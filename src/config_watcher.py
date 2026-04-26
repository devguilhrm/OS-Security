import logging
import time
import threading
from pathlib import Path
from src.fleet_mapping import get_fleet_mapper

logger = logging.getLogger(__name__)

class ConfigHotReloader:
    def __init__(self, config_paths: list[Path], check_interval: int = 30):
        self.config_paths = config_paths
        self.check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mtimes = {str(p): 0 for p in config_paths}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"👁️ ConfigHotReloader iniciado para: {[str(p) for p in self.config_paths]}")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("🛑 ConfigHotReloader finalizado.")

    def _watch_loop(self):
        while self._running:
            try:
                for p in self.config_paths:
                    p_str = str(p)
                    if p.exists():
                        current_mtime = p.stat().st_mtime
                        if current_mtime != self._mtimes.get(p_str, 0):
                            logger.info(f"📄 Alteração detectada: {p.name}")
                            if "fleet_mapping" in p.name:
                                get_fleet_mapper().reload()
                            self._mtimes[p_str] = current_mtime
            except Exception as e:
                logger.error(f"❌ Error in config watcher: {e}")
            time.sleep(self.check_interval)