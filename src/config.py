import os
import re
import json
from pathlib import Path
import pytesseract

class Config:
    # Caminhos
    INPUT_DIR = Path(os.getenv("INPUT_DIR", "input"))
    BASE_DIR = Path(os.getenv("BASE_DIR", "output/ordens"))
    PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", "output/processadas"))
    REVIEW_DIR = Path(os.getenv("REVIEW_DIR", "output/revisao"))
    FLEET_MAPPING_PATH = Path(os.getenv("FLEET_MAPPING_PATH", "data/fleet_mapping.json"))

   
    # Tesseract & OCR
    TESSERACT_PATH = os.getenv(
        "TESSERACT_PATH",
        r"/usr/bin/tesseract" if os.name != "nt" else r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    PLATE_REGEX_MERCOSUL = re.compile(r"^[A-Z]{3}\d[A-Z0-9]\d{2}$")
    PLATE_REGEX_ANTIGO = re.compile(r"^[A-Z]{3}-\d{4}$")
    OCR_CONFIDENCE_THRESHOLD = int(os.getenv("OCR_CONFIDENCE", "65"))
    FILE_STABILITY_WAIT = float(os.getenv("FILE_STABILITY_WAIT", "2.0"))
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    VALIDATE_PLATE_CHECKSUM = os.getenv("VALIDATE_PLATE_CHECKSUM", "true").lower() == "true"
    
    # 🆕 Diretorio para PDFs aguardando assinatura virtual
    SIGNATURE_STAGING_DIR = Path(os.getenv("SIGNATURE_STAGING_DIR", "output/pending_signature"))
    
    # Regex para extrair placa do nome do arquivo (padrão ERP: OS_12345_ABC1D23.pdf ou PLACA.pdf)
    FILE_PLATE_REGEX = re.compile(r"([A-Z]{3}[0-9][A-Z0-9][0-9]{2}|[A-Z]{3}-[0-9]{4})", re.IGNORECASE)
    
    # Performance & Infra
    DB_PATH = Path(os.getenv("DB_PATH", "data/processed.db"))
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "") # Notificação interna (Slack/Discord)

    # 🆕 Integração ERP
    ERP_WEBHOOK_URL = os.getenv("ERP_WEBHOOK_URL", "")
    try:
        ERP_WEBHOOK_HEADERS = json.loads(os.getenv("ERP_WEBHOOK_HEADERS", '{"Content-Type": "application/json", "X-Source": "ocr-automation"}'))
    except json.JSONDecodeError:
        ERP_WEBHOOK_HEADERS = {"Content-Type": "application/json"}
    ERP_WEBHOOK_TIMEOUT = int(os.getenv("ERP_WEBHOOK_TIMEOUT", "5"))

pytesseract.pytesseract.tesseract_cmd = str(Config.TESSERACT_PATH)