import pytest
import numpy as np
import cv2
from pathlib import Path
from src.ocr import preprocess_image, detect_plate, _validate_mercosul
from unittest.mock import patch, MagicMock

class TestOCR:
    @pytest.fixture
    def sample_image(self, tmp_path):
        """Cria imagem sintética com texto simulado"""
        img = np.ones((600, 800, 3), dtype=np.uint8) * 255
        cv2.putText(img, "ABC1D23", (200, 300), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 5)
        path = tmp_path / "test_plate.jpg"
        cv2.imwrite(str(path), img)
        return path

    def test_preprocess_output_shape(self, sample_image):
        gray = cv2.imread(str(sample_image), cv2.IMREAD_GRAYSCALE)
        processed = preprocess_image(gray)
        assert processed.shape[:2] == gray.shape[:2]
        assert processed.dtype == np.uint8

    def test_validate_mercosul_valid(self):
        assert _validate_mercosul("ABC1D23") == True  # Gera hash válido no algoritmo real
        assert _validate_mercosul("DEF5G67") == True

    def test_validate_mercosul_invalid(self):
        assert _validate_mercosul("ABC1D24") == False
        assert _validate_mercosul("INVALID") == False

    def test_detect_plate_fallback_rotation(self, sample_image):
        with patch("src.ocr.pytesseract.image_to_data") as mock_ocr:
            mock_ocr.return_value = {
                "text": ["ABC1D23"], "conf": [85], "left": [100], "top": [100],
                "width": [100], "height": [50], "block_num": [1], "par_num": [1],
                "line_num": [1], "word_num": [1], "text_line": ["ABC1D23"],
                "conf_line": [85], "block_conf": [85], "par_conf": [85]
            }
            plate = detect_plate(sample_image)
            assert plate == "ABC1D23"