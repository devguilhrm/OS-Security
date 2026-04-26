import logging
import cv2
import numpy as np
import pytesseract
from pathlib import Path
from typing import Optional
from src.config import Config

logger = logging.getLogger(__name__)

def _validate_mercosul(plate: str) -> bool:
    """Validação oficial do algoritmo Mercosul (CONTRAN)."""
    if len(plate) != 8 or not Config.PLATE_REGEX_MERCOSUL.match(plate):
        return False
    table = "0123456789ABCDEFGHJKLMNPRTUVWXY"
    weights_1 = [3, 2, 7, 6, 5, 4, 3, 2]
    weights_2 = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]

    sum_1 = sum(table.index(plate[i]) * weights_1[i] for i in range(7))
    check_1 = table[sum_1 % 11] if sum_1 % 11 < 10 else "0"

    sum_2 = sum(table.index(plate[i]) * weights_2[i] for i in range(8))
    check_2 = table[sum_2 % 11] if sum_2 % 11 < 10 else "0"

    return plate[3] == check_1 and plate[6] == check_2

def _validate_old(plate: str) -> bool:
    return len(plate) == 8 and Config.PLATE_REGEX_ANTIGO.match(plate)

def preprocess_image(image: cv2.Mat) -> cv2.Mat:
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    blurred = cv2.medianBlur(gray, 3)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    return cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

def _try_rotate(image: cv2.Mat, angle: int) -> cv2.Mat:
    image_center = tuple(np.array(image.shape[1::-1]) / 2.0)
    rot_mat = cv2.getRotationMatrix2D(image_center, angle, 1.0)
    return cv2.warpAffine(image, rot_mat, image.shape[1::-1], flags=cv2.INTER_LINEAR)

def detect_plate(img_path: Path) -> Optional[str]:
    try:
        img = cv2.imread(str(img_path))
        if img is None:
            raise ValueError(f"Não foi possível ler a imagem: {img_path}")

        candidates = [img]
        for angle in [180, 90, 270]:
            candidates.append(_try_rotate(img, angle))

        for rotated_img in candidates:
            processed = preprocess_image(rotated_img)
            data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

            for word, conf in zip(data["text"], data["conf"]):
                word = word.strip().upper().replace(" ", "")
                if not word or conf < Config.OCR_CONFIDENCE_THRESHOLD:
                    continue

                if Config.PLATE_REGEX_MERCOSUL.match(word) or Config.PLATE_REGEX_ANTIGO.match(word):
                    if Config.VALIDATE_PLATE_CHECKSUM:
                        is_valid = _validate_mercosul(word) if Config.PLATE_REGEX_MERCOSUL.match(word) else _validate_old(word)
                        if not is_valid:
                            continue

                    logger.info(f"Placa validada: {word} (Conf: {conf}%)")
                    return word
        return None
    except Exception as e:
        logger.error(f"Erro crítico no OCR para {img_path.name}: {str(e)}")
        return None