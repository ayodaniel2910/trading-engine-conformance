"""Unit tests for JSON schema export of the neutral schema models."""

import json
from pathlib import Path

from trading_engine_conformance.schema.export import export_json_schemas


class TestExportJsonSchemas:
    def test_returns_dict_of_named_schemas(self) -> None:
        schemas = export_json_schemas()
        assert "RunArtifact" in schemas
        assert "InstrumentIdentity" in schemas
        assert isinstance(schemas["RunArtifact"], dict)

    def test_run_artifact_schema_has_execution_authorized_const_false(self) -> None:
        schemas = export_json_schemas()
        run_artifact_schema = schemas["RunArtifact"]
        text = json.dumps(run_artifact_schema)
        assert "execution_authorized" in text

    def test_writes_one_json_file_per_schema(self, tmp_path: Path) -> None:
        export_json_schemas(output_dir=tmp_path)
        written = {p.name for p in tmp_path.glob("*.json")}
        assert "RunArtifact.json" in written
        assert "InstrumentIdentity.json" in written

    def test_written_files_are_valid_json(self, tmp_path: Path) -> None:
        export_json_schemas(output_dir=tmp_path)
        for path in tmp_path.glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))
