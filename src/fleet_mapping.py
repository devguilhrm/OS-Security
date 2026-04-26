import logging
import json
import re
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from functools import lru_cache
from src.config import Config

logger = logging.getLogger(__name__)

class FleetMapping:
    def __init__(self, mapping_path: Optional[Path] = None):
        self.mapping_path = mapping_path or Config.FLEET_MAPPING_PATH
        self.rules: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._load_rules()

    def _load_rules(self) -> None:
        with self._lock:
            try:
                if not self.mapping_path.exists():
                    logger.warning(f"⚠️ Arquivo de mapeamento não encontrado: {self.mapping_path}")
                    self.rules = [{"type": "default", "company": "GENERIC", "description": "Fallback padrão"}]
                    return

                with open(self.mapping_path, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)

                for rule in self.rules:
                    if rule.get("type") == "regex" and "pattern" in rule:
                        rule["_compiled"] = re.compile(rule["pattern"])

                self.resolve.cache_clear()
                logger.info(f"🗺️ Mapeamento de frotas carregado/atualizado: {len(self.rules)} regras")
            except Exception as e:
                logger.error(f"❌ Falha ao carregar mapeamento: {e}")
                self.rules = [{"type": "default", "company": "GENERIC"}]

    def reload(self) -> None:
        """Recarrega as regras e limpa o cache (thread-safe)"""
        logger.info("🔄 Reloading fleet mapping rules...")
        self._load_rules()

    @lru_cache(maxsize=50000)
    def resolve(self, plate: str) -> str:
        plate_clean = plate.strip().upper().replace("-", "")
        for rule in self.rules:
            r_type = rule.get("type", "default")
            pattern = rule.get("pattern", "")
            company = rule.get("company", "GENERIC")

            if r_type == "prefix":
                if plate_clean.startswith(pattern.upper()):
                    return company
            elif r_type == "regex":
                if rule.get("_compiled") and rule["_compiled"].match(plate_clean):
                    return company
            elif r_type == "exact":
                if plate_clean == pattern.upper():
                    return company
            elif r_type == "default":
                return company
        return "GENERIC"

    def get_rules(self) -> List[Dict[str, Any]]:
        """Retorna regras limpas (sem objetos compilados) para API"""
        with self._lock:
            return [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in self.rules
            ]

_mapper: Optional[FleetMapping] = None

def get_fleet_mapper() -> FleetMapping:
    global _mapper
    if _mapper is None:
        _mapper = FleetMapping()
    return _mapper