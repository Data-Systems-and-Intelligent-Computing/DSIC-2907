import json

import pytest

from src.backbone_freeze import event_schema, normalized_snapshot


def test_event_schema_records_types_and_rejects_field_drift(tmp_path):
    path = tmp_path / "events.jsonl"
    rows = [
        {"event": "download", "job_id": "job_0000", "download_bytes": 12, "transfer_seconds": None},
        {"event": "download", "job_id": "job_0001", "download_bytes": 13, "transfer_seconds": None},
        {"event": "apply", "job_id": "job_0000", "version_after": 1},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    schema = event_schema(path)
    assert schema["download"] == {
        "download_bytes": "int",
        "event": "str",
        "job_id": "str",
        "transfer_seconds": "null",
    }
    assert schema["apply"]["version_after"] == "int"

    rows[1]["download_bytes"] = "13"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event schema"):
        event_schema(path)


def test_normalized_snapshot_ignores_only_run_paths():
    snapshot = {
        "pilot_settings": {
            "seed": 42,
            "max_accepted_updates": 30,
            "run_dir": "run_a",
            "summary_output": "summary_a",
        },
        "backbone": {"max_concurrency": 3},
        "local_training": {"epochs": 1},
        "policy": {"update_budget": 1.0},
        "source_files": {"b0.py": {"sha256": "abc"}},
        "threshold": 0.5,
    }
    other = json.loads(json.dumps(snapshot))
    other["pilot_settings"].update(run_dir="run_b", summary_output="summary_b")
    assert normalized_snapshot(snapshot) == normalized_snapshot(other)
    other["local_training"]["epochs"] = 2
    assert normalized_snapshot(snapshot) != normalized_snapshot(other)
