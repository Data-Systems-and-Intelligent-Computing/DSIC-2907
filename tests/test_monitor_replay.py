import copy
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
from test_b0 import b0_experiment  # noqa: F401

from src.b0 import replay, run_b0
from src.monitor import replay_monitor, verify_monitor
from src.preprocess import artifact_ref, read_json, sha256


@pytest.fixture
def captured(request):
    config_path, config, sources = request.getfixturevalue("b0_experiment")
    run_b0(config_path)
    sources["test"].unlink()
    sources["train"].unlink()
    return Path(config["run_dir"])


def tree_hashes(directory):
    return {str(p.relative_to(directory)): sha256(p) for p in directory.rglob("*") if p.is_file()}


def test_monitor_replay_is_deterministic_read_only_and_preserves_b0(captured, tmp_path):
    before_receipt = replay(captured)
    before_files = tree_hashes(captured)
    before_model = torch.load(captured / "model.pt", weights_only=True)["model_state"]
    torch_rng = torch.get_rng_state().clone()
    numpy_rng, python_rng = np.random.get_state(), random.getstate()
    a = replay_monitor(captured, tmp_path / "monitor_a")
    b = replay_monitor(captured, tmp_path / "monitor_b")
    assert torch.equal(torch_rng, torch.get_rng_state())
    assert np.array_equal(numpy_rng[1], np.random.get_state()[1])
    assert python_rng == random.getstate()
    assert verify_monitor(tmp_path / "monitor_a/manifest.json") == a
    assert verify_monitor(tmp_path / "monitor_b/manifest.json") == b
    assert Path(a["snapshots"]["path"]).read_bytes() == Path(b["snapshots"]["path"]).read_bytes()
    assert {k: v for k, v in a.items() if k != "snapshots"} == {
        k: v for k, v in b.items() if k != "snapshots"
    }
    assert replay(captured) == before_receipt == a["b0_replay"]
    assert tree_hashes(captured) == before_files
    after_model = torch.load(captured / "model.pt", weights_only=True)["model_state"]
    assert all(torch.equal(t, after_model[name]) for name, t in before_model.items())
    assert a["event_count"] == 12
    assert a["snapshot_count"] == 26
    assert a["observation_issues"] == []
    assert a["status_counts"]["rtt_seconds"] == {"unmeasured_process_pool_ipc": 26}
    rows = [json.loads(line) for line in Path(a["snapshots"]["path"]).read_text().splitlines()]
    assert {r["through_event_index"] for r in rows} == set(range(13))
    assert all(
        set(r["fields"])
        == {
            "num_samples",
            "previous_local_train_seconds",
            "rtt_seconds",
            "throughput_bytes_per_second",
            "last_arrival_staleness",
            "contribution_age_seconds",
        }
        for r in rows
    )
    # Each present feature refers only to already available log records.
    events = [json.loads(line) for line in (captured / "events.jsonl").read_text().splitlines()]
    for row in rows:
        for field in row["fields"].values():
            for source in field["source"]:
                assert source["artifact"] in a["inputs"]
                index = source["event_index"]
                assert index <= row["through_event_index"]
                if index:
                    event = events[index - 1]
                    assert source["event"] == event["event"]
                    assert source["job_id"] == event["job_id"]
    # CLI verify reads the exact same bundle.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.monitor",
            "verify",
            "--manifest",
            str(tmp_path / "monitor_a/manifest.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "verified"


def test_monitor_rejects_overwrite_and_input_destinations(captured, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(captured, target_is_directory=True)
    before = tree_hashes(captured)
    for path in (destination, captured, captured / "monitor", alias / "monitor"):
        with pytest.raises((FileExistsError, ValueError)):
            replay_monitor(captured, path)
    assert tree_hashes(captured) == before


def test_verify_recomputes_content_and_detects_tampered_references(captured, tmp_path):
    directory = tmp_path / "monitor"
    report = replay_monitor(captured, directory)
    manifest = directory / "manifest.json"
    snapshots = directory / "snapshots.jsonl"
    original = snapshots.read_bytes()
    rows = snapshots.read_text().splitlines()
    first = json.loads(rows[0])
    first["fields"]["num_samples"]["value"] += 1
    rows[0] = json.dumps(first)
    snapshots.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match="SHA256"):
        verify_monitor(manifest)
    forged = copy.deepcopy(report)
    forged["snapshots"] = artifact_ref(snapshots)
    manifest.write_text(json.dumps(forged))
    with pytest.raises(ValueError, match="snapshot"):
        verify_monitor(manifest)
    snapshots.write_bytes(original)
    for key in ("event_count", "status_counts", "monitor_source", "schema", "inputs", "b0_replay"):
        forged = copy.deepcopy(report)
        if key == "event_count":
            forged[key] += 1
        elif key in ("monitor_source", "schema"):
            forged[key]["sha256"] = "0" * 64
        elif key == "inputs":
            forged[key]["partition"]["sha256"] = "0" * 64
        else:
            forged[key] = {}
        manifest.write_text(json.dumps(forged))
        with pytest.raises(ValueError):
            verify_monitor(manifest)


def test_changed_event_or_partition_invalidates_monitor_evidence(captured, tmp_path):
    output = tmp_path / "monitor"
    report = replay_monitor(captured, output)
    for key in ("events", "partition"):
        path = Path(report["inputs"][key]["path"])
        original = path.read_bytes()
        try:
            path.write_bytes(original + b"\n")
            with pytest.raises(ValueError, match="SHA256"):
                verify_monitor(output / "manifest.json")
        finally:
            path.write_bytes(original)


def test_report_counts_missing_duration_and_rejects_inconsistent_metadata(captured, tmp_path):
    events_path = captured / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    first_arrival = next(event for event in events if event["event"] == "arrival")
    del first_arrival["local_train_seconds"]
    events_path.write_text("".join(json.dumps(event) + "\n" for event in events))
    manifest_path = captured / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["artifacts"]["events"] = artifact_ref(events_path)
    manifest_path.write_text(json.dumps(manifest))
    report = replay_monitor(captured, tmp_path / "missing")
    assert report["observation_issues"] == [
        {
            "client_id": first_arrival["client_id"],
            "event_index": events.index(first_arrival) + 1,
            "field": "previous_local_train_seconds",
            "status": "missing_observation",
        }
    ]
    assert report["status_counts"]["previous_local_train_seconds"]["missing_observation"] > 0
    config_path = captured / "configuration.json"
    config = read_json(config_path)
    partition_path = Path(config["partition_manifest"]["path"])
    partition = read_json(partition_path)
    partition["clients"][partition["client_ids"][0]]["row_count"] += 1
    partition_path.write_text(json.dumps(partition))
    config["partition_manifest"] = artifact_ref(partition_path)
    config_path.write_text(json.dumps(config))
    manifest["artifacts"]["configuration"] = artifact_ref(config_path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="count"):
        replay_monitor(captured, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_nonfinite_json_does_not_receive_a_completed_monitor_manifest(captured, tmp_path):
    path = captured / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    next(e for e in events if e["event"] == "arrival")["local_train_seconds"] = float("nan")
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    manifest_path = captured / "manifest.json"
    manifest = read_json(manifest_path)
    manifest["artifacts"]["events"] = artifact_ref(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid JSON constant"):
        replay_monitor(captured, tmp_path / "nonfinite")
    assert not (tmp_path / "nonfinite/manifest.json").exists()
