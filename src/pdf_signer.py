import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class PDFSigner:
    def __init__(self, cert_path: Path, password: str):
        self.cert_path = cert_path
        self.password = password
        if not cert_path.exists():
            raise FileNotFoundError(f"🔑 Certificado não encontrado: {cert_path}")

    def sign(self, input_pdf: Path, output_pdf: Path, reason: str = "Automação OS", location: str = "Oficina Central") -> bool:
        """Assina PDF usando pdftk (padrão indústria para conformidade ISO 32000-1)"""
        try:
            cmd = [
                "pdftk",
                f"A={input_pdf}",
                "digital_sign_as", str(output_pdf),
                str(self.cert_path),
                self.password,  # pdftk lê a senha do último argumento ou stdin
                reason,
                location
            ]
            
            result = subprocess.run(
                cmd,
                input=self.password.encode("utf-8"),
                capture_output=True,
                timeout=30,
                check=False
            )

            if result.returncode == 0 and output_pdf.exists():
                logger.info(f"✅ PDF assinado com sucesso: {output_pdf.name}")
                return True
            else:
                logger.error(f"❌ pdftk falhou: {result.stderr.decode().strip()}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"⏱️ Timeout ao assinar {input_pdf.name}")
            return False
        except Exception as e:
            logger.error(f"💥 Erro inesperado na assinatura: {e}")
            return False