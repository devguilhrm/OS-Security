import os
import re
import time
import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime


# Pastas do sistema
PASTA_IMAGENS = "imagens_camera"
PASTA_BASE = "ordensdeservico"
PASTA_PROCESSADAS = "processadas"


# Criar pastas automaticamente se não existirem
for pasta in [PASTA_IMAGENS, PASTA_BASE, PASTA_PROCESSADAS]:
    if not os.path.exists(pasta):
        os.makedirs(pasta)


# Função para detectar a placa
def detectar_placa(caminho_imagem):

    img = cv2.imread(caminho_imagem)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    texto = pytesseract.image_to_string(gray)

    texto = texto.upper()

    placa = re.findall(r'[A-Z]{3}[0-9][A-Z0-9][0-9]{2}', texto)

    if placa:
        return placa[0]

    return None


# Função que processa a imagem
def processar_imagem(caminho_imagem):

    placa = detectar_placa(caminho_imagem)

    if not placa:
        print("Placa não detectada:", caminho_imagem)
        return

    # criar pasta do carro
    pasta_carro = os.path.join(PASTA_BASE, placa)

    if not os.path.exists(pasta_carro):
        os.makedirs(pasta_carro)

    # abrir imagem
    imagem = Image.open(caminho_imagem)

    if imagem.mode in ("RGBA", "P"):
        imagem = imagem.convert("RGB")

    # gerar nome do pdf
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_pdf = f"{timestamp}.pdf"

    caminho_pdf = os.path.join(pasta_carro, nome_pdf)

    # salvar pdf
    imagem.save(caminho_pdf, "PDF")

    print("PDF salvo em:", caminho_pdf)

    # mover imagem original
    nome_imagem = os.path.basename(caminho_imagem)
    destino = os.path.join(PASTA_PROCESSADAS, nome_imagem)

    os.rename(caminho_imagem, destino)

    print("Imagem movida para:", destino)


# Classe que observa novas imagens
class ObservadorImagens(FileSystemEventHandler):

    def on_created(self, event):

        if event.is_directory:
            return

        print("Nova imagem detectada:", event.src_path)

        processar_imagem(event.src_path)


# iniciar observador
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
