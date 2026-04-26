import sqlite3
import logging
from pathlib import Path
from src.config import Config

logger = logging.getLogger(__name__)


class DBManager:
    """
    Gerenciador de banco de dados SQLite para:
      - Rastreamento de arquivos processados (OCR)
      - Controle de PDFs aguardando assinatura virtual
      - Auditoria completa de assinaturas aplicadas
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()
        logger.info("✅ DBManager conectado a %s", self.db_path)

    def _init_db(self) -> None:
        """Inicializa o banco com tabelas para processamento, assinatura e auditoria."""
        cursor = self.conn.cursor()

        # Ativa WAL (Write-Ahead Logging) para concorrência segura
        cursor.execute("PRAGMA journal_mode=WAL")
        logger.info("📝 WAL mode ativado para segurança de concorrência")

        # Tabela de arquivos já processados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                plate TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de PDFs aguardando assinatura virtual (fluxo ERP)
        # Estados: awaiting_signature → signed → archived
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT UNIQUE NOT NULL,
                plate TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                status TEXT DEFAULT 'awaiting_signature',
                archived_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabela de auditoria — cada assinatura aplicada é registrada aqui
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signature_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                signature_hash TEXT NOT NULL,
                signatory TEXT NOT NULL,
                role TEXT NOT NULL,
                client_ip TEXT NOT NULL,
                reason TEXT,
                signed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()
        logger.info("✅ Tabelas de banco inicializadas: processed_files, pending_signatures, signature_audit")

    # ---------------------------------------------------------------------------
    # Métodos para processamento de arquivos (OCR)
    # ---------------------------------------------------------------------------

    def is_processed(self, file_hash: str) -> bool:
        """Verifica se um arquivo já foi processado (por hash)."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,))
        result = cursor.fetchone()
        return result is not None

    def register(self, file_hash: str, plate: str = None) -> bool:
        """
        Registra um arquivo como processado.
        Retorna True se inserido, False se já existia.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO processed_files (file_hash, plate) VALUES (?, ?)",
                (file_hash, plate),
            )
            self.conn.commit()
            logger.info("✅ Arquivo registrado: hash=%s, plate=%s", file_hash[:12], plate)
            return True
        except sqlite3.IntegrityError:
            logger.warning("⚠️ Arquivo já processado: hash=%s", file_hash[:12])
            return False
        except Exception as e:
            logger.error("❌ Erro ao registrar arquivo processado: %s", e)
            return False

    # ---------------------------------------------------------------------------
    # Métodos para assinatura virtual
    # ---------------------------------------------------------------------------

    def register_pending_signature(self, file_hash: str, plate: str, pdf_path: Path) -> bool:
        """
        Registra um PDF aguardando assinatura virtual.
        Usado quando o ERP envia um PDF com campo de assinatura vazio.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pending_signatures
                (file_hash, plate, pdf_path, status)
                VALUES (?, ?, ?, ?)
                """,
                (file_hash, plate, str(pdf_path), "awaiting_signature"),
            )
            self.conn.commit()
            logger.info(
                "📄 PDF registrado como aguardando assinatura: plate=%s, path=%s",
                plate, pdf_path.name,
            )
            return True
        except Exception as e:
            logger.error("❌ Falha ao registrar PDF pendente: %s", e)
            return False

    def get_pending_signature(self, plate: str) -> dict:
        """Obtém o registro de um PDF aguardando assinatura por placa."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, file_hash, plate, pdf_path, status, created_at
            FROM pending_signatures
            WHERE plate = ? AND status = 'awaiting_signature'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (plate,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "file_hash": row[1],
                "plate": row[2],
                "pdf_path": row[3],
                "status": row[4],
                "created_at": row[5],
            }
        return None

    def register_signature_audit(
        self,
        file_hash: str,
        pdf_path: str,
        sig_hash: str,
        signatory: str,
        role: str,
        ip: str,
        reason: str = None,
    ) -> bool:
        """
        Registra uma assinatura aplicada em auditoria e marca o PDF como assinado.
        Chamado após aplicar com sucesso a assinatura virtual no PDF.
        """
        try:
            cursor = self.conn.cursor()

            # Insere registro de auditoria
            cursor.execute(
                """
                INSERT INTO signature_audit
                (file_hash, pdf_path, signature_hash, signatory, role, client_ip, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_hash, pdf_path, sig_hash, signatory, role, ip, reason),
            )

            # Marca como assinado na tabela de pendentes
            cursor.execute(
                "UPDATE pending_signatures SET status = 'signed' WHERE file_hash = ?",
                (file_hash,),
            )

            self.conn.commit()
            logger.info(
                "✅ Assinatura auditada: signatory=%s, role=%s, ip=%s",
                signatory, role, ip,
            )
            return True
        except Exception as e:
            logger.error("❌ Falha ao registrar auditoria de assinatura: %s", e)
            return False

    def get_signature_audit(self, file_hash: str) -> dict:
        """Obtém o registro de auditoria de uma assinatura."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, file_hash, pdf_path, signature_hash, signatory, role, client_ip, reason, signed_at
            FROM signature_audit
            WHERE file_hash = ?
            ORDER BY signed_at DESC
            LIMIT 1
            """,
            (file_hash,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0],
                "file_hash": row[1],
                "pdf_path": row[2],
                "signature_hash": row[3],
                "signatory": row[4],
                "role": row[5],
                "client_ip": row[6],
                "reason": row[7],
                "signed_at": row[8],
            }
        return None

    # ---------------------------------------------------------------------------
    # Métodos utilitários
    # ---------------------------------------------------------------------------

    def get_pending_count(self) -> int:
        """Retorna o número de PDFs aguardando assinatura."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM pending_signatures WHERE status = 'awaiting_signature'"
        )
        count = cursor.fetchone()[0]
        return count

    def get_signed_count(self) -> int:
        """Retorna o número total de assinaturas aplicadas."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signature_audit")
        count = cursor.fetchone()[0]
        return count

    def finalize_signature_cycle(self, file_hash: str, archived_path: str = None, company: str = None) -> bool:
        """
        Finaliza o ciclo de assinatura: marca o PDF como 'archived' após ser salvo
        no diretório final. Chamado após process_image() completar o arquivamento.

        Args:
            file_hash: Hash SHA-256 do arquivo
            archived_path: (opcional) Caminho final onde o PDF foi arquivado
            company: (opcional) Código da empresa para auditoria

        Retorna True se atualizado com sucesso, False caso contrário.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE pending_signatures
                SET status = 'archived', archived_at = CURRENT_TIMESTAMP
                WHERE file_hash = ? AND status = 'signed'
                """,
                (file_hash,),
            )
            if cursor.rowcount == 0:
                logger.warning("⚠️ Registro não encontrado para arquivamento: hash=%s", file_hash[:12])
                return False
            self.conn.commit()
            logger.info(
                "✅ Ciclo de assinatura finalizado: hash=%s, archived_path=%s, company=%s",
                file_hash[:12],
                archived_path or "N/A",
                company or "N/A",
            )
            return True
        except Exception as e:
            logger.error("❌ Falha ao finalizar ciclo de assinatura: %s", e)
            return False

    def get_stats(self) -> dict:
        """Retorna estatísticas gerais do banco."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_files")
        processed = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM pending_signatures WHERE status = 'awaiting_signature'"
        )
        pending = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM pending_signatures WHERE status = 'signed'"
        )
        signed = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM pending_signatures WHERE status = 'archived'"
        )
        archived = cursor.fetchone()[0]

        return {
            "total_processed": processed,
            "pending_signatures": pending,
            "signed": signed,
            "archived": archived,
        }

    def close(self) -> None:
        """Fecha a conexão com o banco."""
        if self.conn:
            self.conn.close()
            logger.info("🔒 Conexão com banco de dados encerrada")