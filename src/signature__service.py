import logging
import hashlib
import base64
import io
import time
from pathlib import Path
from typing import Dict, Optional
from fastapi import HTTPException
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from src.database import DBManager
from src.config import Config
import shutil

logger = logging.getLogger(__name__)


class SignatureService:
    """
    Gerencia o ciclo completo de assinatura virtual em PDFs de ordens de serviço.
    
    Fluxo:
      1. Validação segura da imagem de assinatura (PNG em base64)
      2. Localização do PDF aguardando assinatura via banco de dados
      3. Aplicação do overlay (imagem + metadados) ao PDF via ReportLab
      4. Registro de auditoria completo
      5. Arquivamento automático no diretório final
      6. Marcação do ciclo como finalizado no banco
    """

    def __init__(self, db: DBManager):
        self.db = db
        self.signatures_dir = Path("data/signatures_temp")
        self.signatures_dir.mkdir(parents=True, exist_ok=True)
        logger.info("✅ SignatureService inicializado")

    async def apply_virtual_signature(
        self,
        plate: str,
        signature_b64: str,
        signatory_name: str,
        signatory_role: str,
        client_ip: str,
        reason: str,
        pdf_path: Optional[Path] = None,
    ) -> Dict:
        """
        Aplica assinatura virtual em um PDF de OS.

        Args:
            plate: Placa do veículo (ex: ABC1D23)
            signature_b64: Imagem PNG codificada em base64 (com ou sem prefixo data:)
            signatory_name: Nome completo do signatário
            signatory_role: Cargo/função do signatário
            client_ip: IP de origem (para auditoria)
            reason: Motivo da assinatura (ex: "Aceite OS")
            pdf_path: (opcional) Caminho explícito do PDF; se omitido, busca no DB

        Retorna:
            Dict com status="success", caminhos, hashes e timestamps

        Levanta:
            HTTPException(400): Assinatura inválida
            HTTPException(404): PDF não encontrado
            HTTPException(500): Erro ao processar
        """

        # [1] VALIDAÇÃO DE ASSINATURA
        file_hash, sig_bytes = self._validate_signature(signature_b64)

        # [2] LOCALIZAÇÃO DO PDF
        pdf_path, file_hash = self._resolve_pdf_path(plate, pdf_path)

        # [3] APLICAÇÃO DO OVERLAY
        signed_pdf_path = self._apply_overlay(
            pdf_path=pdf_path,
            sig_bytes=sig_bytes,
            file_hash=file_hash,
            signatory_name=signatory_name,
            signatory_role=signatory_role,
            client_ip=client_ip,
            reason=reason,
        )

        # [4] REGISTRO DE AUDITORIA
        sig_hash = self._register_audit(
            file_hash=file_hash,
            pdf_path=signed_pdf_path,
            sig_bytes=sig_bytes,
            signatory_name=signatory_name,
            signatory_role=signatory_role,
            client_ip=client_ip,
            reason=reason,
        )

        # [5] ARQUIVAMENTO E FECHAMENTO DO CICLO
        result = self._archive_and_finalize(
            plate=plate,
            file_hash=file_hash,
            signed_pdf_path=signed_pdf_path,
            sig_hash=sig_hash,
            signatory_name=signatory_name,
        )

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODOS PRIVADOS — CADA ETAPA DO FLUXO
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_signature(self, signature_b64: str) -> tuple:
        """
        Valida e decodifica a imagem de assinatura.
        
        Verifica:
          - Decodificação base64 válida
          - Magic bytes de PNG (89 50 4E 47...)
        
        Retorna:
            (file_hash, sig_bytes): Hash SHA-256 e bytes da imagem
        """
        try:
            # Remove prefixo data:image/png;base64, se presente
            if "," in signature_b64:
                signature_b64 = signature_b64.split(",")[1]

            sig_bytes = base64.b64decode(signature_b64)

            # Valida magic bytes de PNG
            if not sig_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Formato de imagem inválido. Apenas PNG é aceito.")

            # Calcula hash da assinatura para rastreamento
            file_hash = hashlib.sha256(sig_bytes).hexdigest()

            logger.info("✅ Assinatura validada: hash=%s", file_hash[:12])
            return file_hash, sig_bytes

        except Exception as e:
            logger.error("❌ Validação de assinatura falhou: %s", e)
            raise HTTPException(
                status_code=400, detail=f"Assinatura inválida: {str(e)}"
            )

    def _resolve_pdf_path(self, plate: str, explicit_path: Optional[Path]) -> tuple:
        """
        Resolve o caminho do PDF aguardando assinatura.
        
        Prioridade:
          1. Caminho explícito informado
          2. Busca no banco de dados (pending_signatures)
        
        Retorna:
            (pdf_path, file_hash): Caminho do PDF e seu hash
        """
        if explicit_path:
            pdf_path = Path(explicit_path)
            if not pdf_path.exists():
                logger.error("❌ PDF explícito não encontrado: %s", pdf_path)
                raise HTTPException(
                    status_code=404,
                    detail=f"Arquivo PDF não encontrado: {pdf_path.name}",
                )
            return pdf_path, None

        # Busca no banco de dados
        pending = self.db.get_pending_signature(plate.upper())
        if not pending:
            logger.warning("⚠️ Nenhum PDF pendente para placa: %s", plate.upper())
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum PDF pendente encontrado para a placa {plate.upper()}",
            )

        pdf_path = Path(pending["pdf_path"])
        file_hash = pending["file_hash"]

        if not pdf_path.exists():
            logger.error("❌ PDF do banco não encontrado: %s", pdf_path)
            raise HTTPException(
                status_code=404,
                detail=f"Arquivo PDF não encontrado no sistema: {pdf_path.name}",
            )

        logger.info(
            "📄 PDF localizado: plate=%s, path=%s, hash=%s",
            plate.upper(),
            pdf_path.name,
            file_hash[:12],
        )
        return pdf_path, file_hash

    def _apply_overlay(
        self,
        pdf_path: Path,
        sig_bytes: bytes,
        file_hash: str,
        signatory_name: str,
        signatory_role: str,
        client_ip: str,
        reason: str,
    ) -> Path:
        """
        Aplica overlay de assinatura (imagem + metadados) ao PDF.
        
        Processo:
          1. Salva imagem de assinatura temporariamente
          2. Lê PDF original com PyPDF2
          3. Cria canvas com ReportLab (imagem + texto)
          4. Faz merge do overlay na primeira página
          5. Salva PDF assinado localmente
        
        Retorna:
            signed_pdf_path: Caminho do PDF assinado (local)
        """
        sig_filename = f"{file_hash}_sig.png"
        sig_path = self.signatures_dir / sig_filename

        try:
            # Salva imagem temporária
            sig_path.write_bytes(sig_bytes)
            logger.info("📝 Imagem de assinatura salva temporariamente: %s", sig_filename)

            # Lê PDF original
            reader = PdfReader(str(pdf_path))
            writer = PdfWriter()
            writer.append_pages_from_reader(reader)

            # Cria overlay com canvas (ReportLab)
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=A4)
            page_w, page_h = A4

            # Desenha imagem de assinatura no canto inferior direito
            c.drawImage(str(sig_path), page_w - 260, 60, width=220, height=70)

            # Adiciona metadados
            c.setFont("Helvetica", 8)
            c.drawString(page_w - 260, 50, f"{signatory_name} | {signatory_role}")
            c.drawString(page_w - 260, 40, f"Motivo: {reason}")
            c.drawString(page_w - 260, 30, f"IP: {client_ip}")
            c.save()

            # Faz merge do overlay na primeira página
            packet.seek(0)
            overlay = PdfReader(packet)
            writer.pages[0].merge_page(overlay.pages[0])

            # Salva PDF assinado
            signed_pdf_path = pdf_path.with_stem(pdf_path.stem + "_signed_virtual")
            with open(signed_pdf_path, "wb") as f:
                writer.write(f)

            logger.info("✅ Overlay aplicado: %s", signed_pdf_path.name)
            return signed_pdf_path

        except Exception as e:
            logger.error("❌ Falha ao aplicar overlay: %s", e)
            raise HTTPException(
                status_code=500, detail="Erro ao aplicar assinatura no PDF"
            )
        finally:
            # Limpa arquivo temporário
            sig_path.unlink(missing_ok=True)

    def _register_audit(
        self,
        file_hash: str,
        pdf_path: Path,
        sig_bytes: bytes,
        signatory_name: str,
        signatory_role: str,
        client_ip: str,
        reason: str,
    ) -> str:
        """
        Registra a assinatura aplicada em auditoria no banco.
        
        Marca o registro em pending_signatures como 'signed'.
        
        Retorna:
            sig_hash: Hash SHA-256 da imagem de assinatura
        """
        sig_hash = hashlib.sha256(sig_bytes).hexdigest()

        audit_ok = self.db.register_signature_audit(
            file_hash=file_hash,
            pdf_path=str(pdf_path),
            sig_hash=sig_hash,
            signatory=signatory_name,
            role=signatory_role,
            ip=client_ip,
            reason=reason,
        )

        if not audit_ok:
            logger.error("❌ Falha ao registrar auditoria")
            raise HTTPException(
                status_code=500, detail="Erro ao registrar auditoria de assinatura"
            )

        logger.info(
            "✅ Auditoria registrada: signatory=%s, sig_hash=%s",
            signatory_name,
            sig_hash[:12],
        )
        return sig_hash

    def _archive_and_finalize(
        self,
        plate: str,
        file_hash: str,
        signed_pdf_path: Path,
        sig_hash: str,
        signatory_name: str,
    ) -> Dict:
        """
        Arquiva o PDF assinado e finaliza o ciclo de assinatura.
        
        Processo:
          1. Cria diretório de destino
          2. Move PDF para arquivo final
          3. Marca ciclo como 'archived' no banco
        
        Se o arquivamento falhar, a auditoria permanece válida (não eleva exceção).
        
        Retorna:
            dict com status, caminhos, hashes e timestamps
        """
        timestamp = time.time()
        result = {
            "status": "success",
            "signed_pdf": signed_pdf_path.name,
            "signature_hash": sig_hash,
            "plate": plate.upper(),
            "timestamp": timestamp,
            "signatory": signatory_name,
            "archived": False,
            "archived_path": None,
        }

        try:
            # Cria diretório de destino
            Config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

            # Move PDF para arquivo final
            dest_archive = Config.PROCESSED_DIR / signed_pdf_path.name
            shutil.move(str(signed_pdf_path), str(dest_archive))
            logger.info("📦 PDF movido para arquivo: %s", dest_archive.name)

            # Marca ciclo como finalizado no banco
            company = "VIRTUAL_SIGN"  # Em produção: resolver via DB ou mapeamento de placa
            finalize_ok = self.db.finalize_signature_cycle(
                file_hash=file_hash,
                archived_path=str(dest_archive),
                company=company,
            )

            if finalize_ok:
                result["archived"] = True
                result["archived_path"] = str(dest_archive)
                logger.info(
                    "✅ Ciclo finalizado: plate=%s, archived=%s",
                    plate.upper(),
                    dest_archive.name,
                )
            else:
                logger.warning(
                    "⚠️ PDF arquivado mas ciclo não finalizado no DB: %s",
                    dest_archive.name,
                )

        except Exception as e:
            logger.warning(
                "⚠️ Falha no arquivamento (assinatura já é válida e auditável): %s", e
            )
            result["archive_warning"] = str(e)

        return result