import pytest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from src.config import Config
from src.pipeline import process_image

import pytest
import shutil
from pathlib import Path
from src.pipeline import _calculate_hash, route_document
from src.config import Config

class TestPipeline:
    def test_calculate_hash_deterministic(self, tmp_path):
        file = tmp_path / "test.txt"
        file.write_text("content")
        h1 = _calculate_hash(file)
        h2 = _calculate_hash(file)
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex length

    def test_calculate_hash_changes_with_content(self, tmp_path):
        f1 = tmp_path / "a.txt"; f1.write_text("a")
        f2 = tmp_path / "b.txt"; f2.write_text("b")
        assert _calculate_hash(f1) != _calculate_hash(f2)

    def test_route_document_pdf_to_staging(self, tmp_path, db_manager):
        from src.api import db_manager as api_db
        import src.api
        src.api.db_manager = db_manager

        pdf = tmp_path / "os_ABC1D23.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")
        Config.INPUT_DIR = tmp_path / "input"; Config.INPUT_DIR.mkdir()
        Config.SIGNATURE_STAGING_DIR = tmp_path / "staging"

        route_document(pdf, "ABC1D23")
        assert (Config.SIGNATURE_STAGING_DIR / pdf.name).exists()

    def test_route_document_image_to_ocr_queue(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\x89PNG fake image")
        Config.INPUT_DIR = tmp_path / "input"; Config.INPUT_DIR.mkdir()
        
        # Simula roteamento para imagem (chama submit_for_processing mock)
        with patch("src.pipeline.submit_for_processing") as mock_proc:
            route_document(img)
            mock_proc.assert_called_once_with(img)

    @pytest.fixture
    def temp_dirs(tmp_path):
        Config.BASE_DIR = tmp_path / "ordens"
        Config.PROCESSED_DIR = tmp_path / "processadas"
        Config.REVIEW_DIR = tmp_path / "revisao"
        Config.BASE_DIR.mkdir(parents=True)
        Config.PROCESSED_DIR.mkdir(parents=True)
        Config.REVIEW_DIR.mkdir(parents=True)
        return tmp_path

    @pytest.fixture
    def fake_image_path(tmp_path):
        img_path = tmp_path / "test_car.jpg"
        img = Image.new("RGB", (100, 100), color="red")
        img.save(img_path)
        return img_path

    def test_process_image_success(temp_dirs, fake_image_path):
        with patch("src.pipeline.detect_plate") as mock_detect:
            mock_detect.return_value = "ABC1D23"
            result = process_image(fake_image_path)
            assert result is True
            assert (temp_dirs / "ordens" / "ABC1D23").is_dir()
            assert any((temp_dirs / "ordens" / "ABC1D23").glob("*.pdf"))
            assert not fake_image_path.exists()
            assert (temp_dirs / "processadas" / "test_car.jpg").exists()

    def test_process_image_no_plate(temp_dirs, fake_image_path):
        with patch("src.pipeline.detect_plate", return_value=None):
            result = process_image(fake_image_path)
            assert result is False
            assert not fake_image_path.exists()
            assert (temp_dirs / "revisao" / "test_car.jpg").exists()

    def test_process_image_pdf_error(temp_dirs, fake_image_path):
        with patch("src.pipeline.detect_plate", return_value="ABC1D23"), \
            patch("PIL.Image.open", side_effect=Exception("Corrupt")):
            result = process_image(fake_image_path)
            assert result is False
            assert (temp_dirs / "revisao" / "test_car.jpg").exists()