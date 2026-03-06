import pyautogui
import time
import os
import re
import cv2
import pytesseract

from PIL import Image #transforma a imagem em pdf
from watchdog.observers import Observer #mudanças nos arquivos
from watchdog.events import FileSystemEventHandler #events faz com que a biblioteca reaja a uma mudança
from datetime import datetime

PASTA_IMAGENS = "imagens_camera"
PASTA_BASE = "ordensdeserviço"
PASTA_PROCESSADAS = "processadas"

def detectar_placa(caminho_imagem):
    img = cv2.imread(caminho_imagem)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    texto = pytesseract.image_to_string(gray)
    texto = texto.upper()
    placa = re.findall(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}', texto)
    if placa:
        return placa[0]
    
    return None

def processar_imagem(caminho_imagem):

    placa = detectar_placa(caminho_imagem)

    if not placa:
        print("Placa não encontrada")
        return

    pasta_carro = os.path.join(PASTA_BASE, placa)

    if not os.path.exists(pasta_carro):
        os.makedirs(pasta_carro)

    imagem = Image.open(caminho_imagem)

    if imagem.mode != "RGB":
        imagem = imagem.convert("RGB")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    nome_pdf = f"{timestamp}.pdf"

    caminho_pdf = os.path.join(pasta_carro, nome_pdf)

    imagem.save(caminho_pdf)

    print("PDF criado:", caminho_pdf)

    destino = os.path.join(PASTA_PROCESSADAS, os.path.basename(caminho_imagem))

    os.rename(caminho_imagem, destino)

class ObservadorImagens(FileSystemEventHandler):

    def on_created(self, event):

        if event.is_directory:
            return

        caminho = event.src_path

        print("Nova imagem detectada:", caminho)

        processar_imagem(caminho)

        
observer = Observer()

handler = ObservadorImagens()

observer.schedule(handler, PASTA_IMAGENS, recursive=False)

observer.start()

print("Sistema iniciado. Observando pasta:", PASTA_IMAGENS)

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    observer.stop()

observer.join()
