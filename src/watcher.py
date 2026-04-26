import logging
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
from src.config import Config
from src.api import submit_for_processing

logger = logging.getLogger(__name__)

class ImageHandler(FileSystemEventHandler):
    def on_closed(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix.lower() not in Config.SUPPORTED_EXTENSIONS:
            return

        logger.info(f"🔍 Watchdog: {file_path.name}")
        time.sleep(Config.FILE_STABILITY_WAIT)

        if file_path.exists():
            submit_for_processing(file_path)
        else:
            logger.debug(f"⏭️ Arquivo desaparecido antes do processamento: {file_path.name}")