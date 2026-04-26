#!/usr/bin/env python3
import argparse
import json
import logging
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

def calculate_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def generate_billing_pack(company: str, month: str, output_dir: Path) -> None:
    base_dir = Path("output/ordens") / company
    if not base_dir.exists():
        logger.error(f"❌ Diretório não encontrado: {base_dir}")
        return

    month_match = month.replace("-", "")
    pdf_files = list(base_dir.rglob(f"*_{month_match}*.pdf"))
    pdf_files.sort()

    if not pdf_files:
        logger.warning(f"⚠️ Nenhum PDF encontrado para {company} no mês {month}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_filename = f"relatorio_{company}_{month}.zip"
    zip_path = output_dir / zip_filename
    manifest: List[Dict] = []

    logger.info(f"📦 Gerando {zip_filename} ({len(pdf_files)} arquivos)...")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            arcname = pdf.relative_to(base_dir)
            zf.write(pdf, arcname)
            manifest.append({
                "filename": pdf.name,
                "plate": pdf.stem.split("_")[0] if "_" in pdf.stem else "UNKNOWN",
                "timestamp": datetime.now().isoformat(),
                "sha256": calculate_hash(pdf),
                "relative_path": str(arcname)
            })

    manifest_path = output_dir / f"relatorio_{company}_{month}_index.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "company": company,
            "month": month,
            "generated_at": datetime.now().isoformat(),
            "total_files": len(manifest),
            "zip_file": zip_filename,
            "files": manifest
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Pacote gerado: {zip_path}")
    logger.info(f"📄 Índice JSON: {manifest_path}")

def main():
    parser = argparse.ArgumentParser(description="Gera pacote mensal de faturamento por locadora")
    parser.add_argument("--company", required=True, help="Código da locadora (ex: LOCADORA_A)")
    parser.add_argument("--month", required=True, help="Mês no formato YYYY-MM (ex: 2024-10)")
    parser.add_argument("--output-dir", type=Path, default="billing_packages", help="Diretório de saída")
    args = parser.parse_args()
    generate_billing_pack(args.company, args.month, args.output_dir)

if __name__ == "__main__":
    main()