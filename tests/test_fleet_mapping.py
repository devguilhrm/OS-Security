import json
from pathlib import Path
from src.fleet_mapping import FleetMapping

class TestFleetMapping:
    def test_resolve_prefix(self, fleet_mapper):
        assert fleet_mapper.resolve("ABC1D23") == "LOCADORA_A"
        assert fleet_mapper.resolve("ABC-0000") == "LOCADORA_A"

    def test_resolve_exact(self, fleet_mapper):
        assert fleet_mapper.resolve("GOV1234") == "FROTA_GOV"

    def test_resolve_default(self, fleet_mapper):
        assert fleet_mapper.resolve("XYZ5K67") == "GENERIC"
        assert fleet_mapper.resolve("invalid") == "GENERIC"

    def test_case_insensitive(self, fleet_mapper):
        assert fleet_mapper.resolve("abc1d23") == "LOCADORA_A"
        assert fleet_mapper.resolve("AbC-1d23") == "LOCADORA_A"

    def test_reload_updates_rules(self, fleet_mapper, tmp_path):
        mapping_file = tmp_path / "fleet_mapping.json"
        mapping_file.write_text("""[{"type": "prefix", "pattern": "DEF", "company": "LOCADORA_B"}]""")
        fleet_mapper.mapping_path = mapping_file
        fleet_mapper.reload()
        assert fleet_mapper.resolve("DEF1G23") == "LOCADORA_B"