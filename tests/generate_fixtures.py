#!/usr/bin/env python3
"""Gera arquivos de teste sintéticos.

Uso:
    python tests/generate_fixtures.py
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ensure_fixtures_dir() -> Path:
    """Cria o diretório de fixtures, se necessário."""
    FIXTURES_DIR.mkdir(exist_ok=True)
    return FIXTURES_DIR


def generate_plate_image(output_dir: Path) -> None:
    """Gera uma imagem JPEG com uma placa legível."""
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, 40)
    except OSError:
        font = ImageFont.load_default()

    draw.text((250, 250), "ABC1D23", fill="black", font=font)
    img.save(output_dir / "test_plate.jpg", quality=95)


def generate_minimal_pdf(output_dir: Path) -> None:
    """Gera um PDF mínimo e válido para testes."""
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF"
    )

    (output_dir / "test_os.pdf").write_bytes(pdf_bytes)


def generate_signature_base64(output_dir: Path) -> None:
    """Gera uma assinatura PNG codificada em Base64."""
    sig_img = Image.new("RGBA", (200, 50), color=(0, 0, 0, 255))

    buffer = io.BytesIO()
    sig_img.save(buffer, format="PNG")

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    (output_dir / "signature_base64.txt").write_text(encoded, encoding="utf-8")


def generate_fleet_mapping(output_dir: Path) -> None:
    """Gera um arquivo de mapeamento de frotas para testes."""
    mapping = [
        {"type": "prefix", "pattern": "ABC", "company": "LOCADORA_A"},
        {
            "type": "regex",
            "pattern": r"^GOV[0-9][A-Z0-9][0-9]{2}$",
            "company": "FROTA_GOV",
        },
        {"type": "default", "pattern": "", "company": "GENERIC"},
    ]

    with open(output_dir / "fleet_mapping_test.json", "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)


def main() -> None:
    output_dir = ensure_fixtures_dir()

    generate_plate_image(output_dir)
    generate_minimal_pdf(output_dir)
    generate_signature_base64(output_dir)
    generate_fleet_mapping(output_dir)

    print(f"✅ Fixtures gerados em: {output_dir}")


if __name__ == "__main__":
    main()
