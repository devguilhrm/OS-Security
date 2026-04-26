import sys
import signal
import logging
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
import uvicorn
from src.config import Config
from src.watcher import ImageHandler
from src.database import DBManager
from src.api import app, db_manager as api_db, executor as api_executor
from src.config_watcher import ConfigHotReloader
from src.metrics import *  # Garante registro das métricas no registro global

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def verify_directories():
    for d in [Config.INPUT_DIR, Config.BASE_DIR, Config.PROCESSED_DIR, Config.REVIEW_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def check_tesseract():
    import pytesseract
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        logging.critical(f"❌ Tesseract indisponível: {e}")
        sys.exit(1)

def main():
    setup_logging()
    check_tesseract()
    verify_directories()

    api_db = DBManager(Config.DB_PATH)
    api_executor = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)

    # Inicializa hot-reload de configurações
    config_watcher = ConfigHotReloader([Config.FLEET_MAPPING_PATH], check_interval=30)
    config_watcher.start()

    enable_watchdog = os.getenv("ENABLE_WATCHDOG", "true").lower() == "true"
    if enable_watchdog:
        observer = Observer()
        handler = ImageHandler()
        observer.schedule(handler, str(Config.INPUT_DIR), recursive=False)
        observer.start()
        logging.info(f"👁️ Watchdog ativo: {Config.INPUT_DIR.absolute()}")

    api_port = int(os.getenv("API_PORT", "8000"))
    logging.info(f"🚀 FastAPI iniciando na porta {api_port} | Workers: {Config.MAX_WORKERS} | Webhook: {'Ativo' if Config.WEBHOOK_URL else 'Desativado'}")

    def shutdown(signum, frame):
        logging.info("🛑 Sinal de encerramento recebido. Drenando tarefas...")
        if enable_watchdog:
            observer.stop()
            observer.join()
        config_watcher.stop()
        api_executor.shutdown(wait=True, cancel_futures=False)
        api_db.close()
        logging.info("✅ Serviço finalizado com segurança.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        uvicorn.run(app, host="0.0.0.0", port=api_port, log_level="info")
    except KeyboardInterrupt:
        shutdown(None, None)

if __name__ == "__main__":
    main()