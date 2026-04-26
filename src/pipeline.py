import hashlib
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import threading
import requests
from datetime import datetime, timezone
from pathlib import Path
from src.config import Config

import requests
from PIL import Image

from src.config import Config
from src.database import DBManager
from src.fleet_mapping import get_fleet_mapper
from src.ocr import detect_plate
from src.pdf_signer import PDFSigner

logger = logging.getLogger(__name__)

_SIGNER: Optional[PDFSigner] = None


def calculate_file_hash(file_path: Path) -> str:
    """Calculate the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def send_erp_webhook(
    plate: str,
    status: str,
    filename: str,
    pdf_path: Optional[Path],
    company: str,
) -> None:
    """Send an asynchronous event notification to the ERP system."""
    if not Config.ERP_WEBHOOK_URL:
        return

    payload = {
        "event": "ocr_plate_processed",
        "plate": plate,
        "company": company,
        "status": status,
        "filename": filename,
        "pdf_relative_path": (
            str(pdf_path.relative_to(Config.BASE_DIR))
            if pdf_path and pdf_path.exists()
            else None
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": "ocr-automation-service",
    }

    def post_webhook() -> None:
        try:
            response = requests.post(
                Config.ERP_WEBHOOK_URL,
                json=payload,
                headers=Config.ERP_WEBHOOK_HEADERS,
                timeout=Config.ERP_WEBHOOK_TIMEOUT,
            )

            if response.status_code >= 400:
                logger.warning(
                    "ERP webhook returned %s: %s",
                    response.status_code,
                    response.text[:100],
                )
        except Exception:
            logger.exception("ERP webhook failed, but processing will continue")

    threading.Thread(target=post_webhook, daemon=True).start()


def convert_image_to_pdf(image_path: Path, output_path: Path) -> None:
    """Convert an image to PDF, handling transparency correctly."""
    with Image.open(image_path) as image:
        if image.mode in {"RGBA", "LA", "P"}:
            if image.mode == "P":
                image = image.convert("RGBA")

            background = Image.new("RGB", image.size, (255, 255, 255))
            alpha_channel = image.split()[-1] if image.mode in {"RGBA", "LA"} else None
            background.paste(image, mask=alpha_channel)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.save(output_path, "PDF", resolution=150.0)


def get_signer() -> Optional[PDFSigner]:
    """Return a lazily initialized PDF signer instance."""
    global _SIGNER

    if _SIGNER is not None:
        return _SIGNER

    cert_path = os.getenv("SIGN_CERT_PATH", "")
    cert_password = os.getenv("SIGN_CERT_PASSWORD", "")

    if not cert_path or not cert_password:
        return None

    try:
        _SIGNER = PDFSigner(Path(cert_path), cert_password)
    except Exception:
        logger.exception("PDF signing disabled due to certificate initialization error")
        return None

    return _SIGNER


def sign_pdf_if_configured(pdf_path: Path) -> Path:
    """Digitally sign the PDF when a valid certificate is configured."""
    signer = get_signer()
    if signer is None:
        return pdf_path

    signed_pdf_path = pdf_path.with_suffix(".signed.pdf")

    if signer.sign_pdf(pdf_path, signed_pdf_path):
        pdf_path.unlink(missing_ok=True)
        logger.info("Signed PDF generated: %s", signed_pdf_path.name)
        return signed_pdf_path

    logger.warning("PDF signing failed. Using unsigned file.")
    return pdf_path


def archive_file(source: Path, destination_dir: Path) -> None:
    """Move a file to the target directory."""
    destination_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination_dir / source.name))


def process_image(image_path: Path, db: DBManager) -> bool:
    """Process an image, extract a license plate, and generate a signed PDF."""
    file_hash = calculate_file_hash(image_path)

    if db.is_processed(file_hash):
        logger.info("File already processed: %s", image_path.name)
        archive_file(image_path, Config.PROCESSED_DIR)
        return True

    logger.info("Starting processing: %s", image_path.name)

    plate = detect_plate(image_path)
    if not plate:
        logger.warning("No plate detected: %s", image_path.name)
        archive_file(image_path, Config.REVIEW_DIR)
        send_erp_webhook("N/A", "review", image_path.name, None, "UNKNOWN")
        return False

    company = get_fleet_mapper().resolve(plate)
    logger.info("Plate %s mapped to fleet %s", plate, company)

    vehicle_dir = Config.BASE_DIR / company / plate
    vehicle_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = vehicle_dir / f"{plate}_{timestamp}.pdf"

    try:
        convert_image_to_pdf(image_path, pdf_path)
        pdf_path = sign_pdf_if_configured(pdf_path)

        db.register(file_hash, plate)
        send_erp_webhook(plate, "success", image_path.name, pdf_path, company)

        logger.info("PDF generated successfully: %s", pdf_path)
        archive_file(image_path, Config.PROCESSED_DIR)
        return True

    except Exception:
        logger.exception("Failed to process image: %s", image_path.name)
        archive_file(image_path, Config.REVIEW_DIR)
        send_erp_webhook(plate, "failure", image_path.name, None, company)
        return False
    
def trigger_cycle_closure_webhook(plate: str, company: str, signed_pdf_path: Path, sig_hash: str) -> None:
    """Notifica o ERP sobre o fechamento completo do ciclo da OS (assinado + arquivado)"""
    if not Config.ERP_WEBHOOK_URL:
        return
    
    payload = {
        "event": "os_cycle_closed",
        "plate": plate,
        "company": company,
        "status": "closed",
        "signed_pdf_relative_path": str(signed_pdf_path.relative_to(Config.PROCESSED_DIR)),
        "signature_hash": sig_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system": "ocr-automation-service"
    }

    def _post():
        try:
            resp = requests.post(
                Config.ERP_WEBHOOK_URL,
                json=payload,
                headers=Config.ERP_WEBHOOK_HEADERS,
                timeout=Config.ERP_WEBHOOK_TIMEOUT
            )
            if resp.status_code >= 400:
                logger.warning(f"⚠️ ERP Webhook (cycle_close) retornou {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.error(f"❌ Webhook de fechamento falhou (não bloqueia arquivamento): {e}")

    threading.Thread(target=_post, daemon=True).start()