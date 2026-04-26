import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.config import Config
from src.database import DBManager
from src.fleet_mapping import FleetMapping
from src.signature_service import SignatureService
from fastapi.testclient import TestClient
from src.api import app

@pytest.fixture(autouse=True)
def isolate_config():
    """Isola config para testes, apontando para tmp dir"""
    tmpdir = tempfile.mkdtemp()
    original = {}
    for attr in dir(Config):
        if attr.isupper():
            original[attr] = getattr(Config, attr)
            if isinstance(getattr(Config, attr), Path):
                new_path = Path(tmpdir) / original[attr].name
                new_path.parent.mkdir(parents=True, exist_ok=True)
                setattr(Config, attr, new_path)
    yield
    for attr, val in original.items():
        setattr(Config, attr, val)
    shutil.rmtree(tmpdir, ignore_errors=True)

@pytest.fixture
def db_manager(tmp_path):
    """DB in-memory isolado por teste"""
    Config.DB_PATH = tmp_path / "test.db"
    db = DBManager(Config.DB_PATH)
    yield db
    db.close()

@pytest.fixture
def fleet_mapper(tmp_path):
    mapping_file = tmp_path / "fleet_mapping.json"
    mapping_file.write_text("""[
        {"type": "prefix", "pattern": "ABC", "company": "LOCADORA_A"},
        {"type": "exact", "pattern": "GOV1234", "company": "FROTA_GOV"},
        {"type": "default", "pattern": "", "company": "GENERIC"}
    ]""")
    mapper = FleetMapping(mapping_file)
    return mapper

@pytest.fixture
def signature_service(db_manager):
    return SignatureService(db_manager)

@pytest.fixture
def client(db_manager):
    """TestClient com DB isolado"""
    from src.api import db_manager as api_db, sig_service
    with patch.object(app.state, 'db_manager', db_manager):
        with patch.object(app.state, 'sig_service', SignatureService(db_manager)):
            yield TestClient(app)