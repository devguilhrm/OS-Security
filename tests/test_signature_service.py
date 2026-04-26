import base64
import io
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from PIL import Image

from src.signature_service import SignatureService


class TestSignatureService:
    @pytest.fixture
    def valid_png_base64(self) -> str:
        """Gera uma assinatura PNG válida em Base64."""
        img_buffer = io.BytesIO()
        Image.new("RGBA", (200, 50), color="white").save(img_buffer, format="PNG")
        return base64.b64encode(img_buffer.getvalue()).decode()

    def test_invalid_base64_rejected(self, signature_service: SignatureService) -> None:
        """Deve rejeitar payload que não seja Base64 válido."""
        with pytest.raises(HTTPException, match="Assinatura inválida"):
            signature_service.apply_virtual_signature(
                plate="ABC1D23",
                signature_b64="notbase64",
                signatory_name="X",
                signatory_role="Y",
                client_ip="1.2.3.4",
                reason="Test",
            )

    def test_non_png_rejected(self, signature_service: SignatureService) -> None:
        """Deve rejeitar imagens que não sejam PNG."""
        fake_jpg = base64.b64encode(b"\xFF\xD8\xFF\xE0 fake jpg").decode()

        with pytest.raises(HTTPException, match="Formato de imagem inválido"):
            signature_service.apply_virtual_signature(
                plate="ABC1D23",
                signature_b64=fake_jpg,
                signatory_name="X",
                signatory_role="Y",
                client_ip="1.2.3.4",
                reason="Test",
            )

    def test_audit_trail_registered(
        self,
        signature_service: SignatureService,
        valid_png_base64: str,
        tmp_path,
    ) -> None:
        """Deve registrar trilha de auditoria após assinatura válida."""
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (str(pdf), "hash123")
        mock_cursor.execute.return_value = None

        signature_service.db.conn.cursor = MagicMock(return_value=mock_cursor)

        result = signature_service.apply_virtual_signature(
            plate="ABC1D23",
            signature_b64=valid_png_base64,
            signatory_name="Joao",
            signatory_role="Operador",
            client_ip="192.168.1.10",
            reason="Aceite",
        )

        assert result["status"] == "success"
        assert "signature_hash" in result
        assert result["plate"] == "ABC1D23"
