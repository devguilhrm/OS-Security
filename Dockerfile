FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    default-jre-headless \
    pdftk-java \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/input", "/app/output", "/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')" || exit 1

CMD ["python", "-u", "src/main.py"]