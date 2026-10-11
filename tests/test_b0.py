import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import numpy as np
import pytest
import torch
import yaml

from src import partition as part
from src import preprocess as pp
from src.async_server import AsyncServer
from src.client import deserialize_message, serialize_message


def test_fast_client_is_applied_and_redispatched_while_slow_client_is_training(tmp_path):
    from src.b0 import run_async

    release_slow = Event()
    model = torch.nn.Linear(2, 1, bias=False)
    server = AsyncServer(model, total_samples=4)
    data = {client: (np.zeros((2, 2)), np.array([0, 1])) for client in ("fast", "slow")}

    def controlled_train(payload, local_data, model_config, cpu_threads):
        download = deserialize_message(payload)
        if download["client_id"] == "slow":
            assert release_slow.wait(5), (
                "Server waited for slow client instead of applying fast updates"
            )
        update = {
            key: download[key]
            for key in ("job_id", "client_id", "model_start_version", "training_seed")
        }
        update.update(
            num_samples=2,
            budget=1.0,
            local_train_seconds=0.0,
            training_bce_by_epoch=[0.5],
            delta={name: torch.ones_like(t) for name, t in download["model_state"].items()},
        )
        return serialize_message(update), 0.0

    def applied(total_bytes):
        if server.version == 2:
            release_slow.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        result = run_async(
            server,
            data,
            {},
            {"seed": 42, "max_accepted_updates": 3, "max_concurrency": 2, "cpu_threads": 1},
            tmp_path,
            on_apply=applied,
            executor=executor,
            train_fn=controlled_train,
        )
    applies = [e for e in result["events"] if e["event"] == "apply"]
    assert [e["client_id"] for e in applies] == ["fast", "fast", "slow"]
    assert [e["model_start_version"] for e in applies] == [0, 1, 0]
    assert [e["version_before"] for e in applies] == [0, 1, 2]
    assert [e["version_after"] for e in applies] == [1, 2, 3]
    assert [e["staleness"] for e in applies] == [0, 0, 2]
    assert applies[0]["budget"] == 1.0
    arrivals = [e for e in result["events"] if e["event"] == "arrival"]
    assert [e["model_start_version"] for e in arrivals] == [0, 1, 0]
    assert [e["server_version"] for e in arrivals] == [0, 1, 2]
    assert [e["staleness"] for e in arrivals] == [0, 0, 2]
    assert result["staleness_summary"]["run"] == {
        "count": 3,
        "minimum": 0,
        "mean": pytest.approx(2 / 3),
        "median": 0.0,
        "p95": pytest.approx(1.8),
        "maximum": 2,
    }
    assert result["staleness_summary"]["clients"]["fast"]["maximum"] == 0
    assert result["staleness_summary"]["clients"]["slow"]["maximum"] == 2
    downloads = [e for e in result["events"] if e["event"] == "download"]
    assert downloads[2]["model_start_version"] == 1
    logged = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert logged == result["events"]
    for event in downloads:
        assert event["download_bytes"] == len((tmp_path / event["payload_file"]).read_bytes())


def test_staleness_summary_keeps_zero_update_client():
    from src.b0 import summarize_staleness

    result = summarize_staleness([{"client_id": "fast", "staleness": 2}], ["fast", "idle"])
    assert result["run"]["count"] == 1
    assert result["clients"]["fast"]["mean"] == 2.0
    assert result["clients"]["idle"] == {
        "count": 0,
        "minimum": None,
        "mean": None,
        "median": None,
        "p95": None,
        "maximum": None,
    }
    assert json.dumps(result, allow_nan=False)


def test_invalid_arrival_is_rejected_without_advancing_version(tmp_path):
    from src.b0 import run_async

    model = torch.nn.Linear(2, 1, bias=False)
    before = {name: tensor.clone() for name, tensor in model.state_dict().items()}
    server = AsyncServer(model, total_samples=2)

    def invalid_train(payload, local_data, model_config, cpu_threads):
        download = deserialize_message(payload)
        payload = serialize_message(
            {
                **{
                    key: download[key]
                    for key in ("job_id", "client_id", "model_start_version", "training_seed")
                },
                "num_samples": 2,
                "budget": 1.0,
                "local_train_seconds": 0.0,
                "training_bce_by_epoch": [0.5],
                "delta": {
                    name: torch.full_like(tensor, float("nan")) for name, tensor in before.items()
                },
            }
        )
        return payload, 0.0

    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ValueError, match="Invalid update tensor"):
            run_async(
                server,
                {"client_0": (np.zeros((2, 2)), np.array([0, 1]))},
                {},
                {"seed": 42, "max_accepted_updates": 1, "max_concurrency": 1, "cpu_threads": 1},
                tmp_path,
                executor=executor,
                train_fn=invalid_train,
            )
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    arrival, reject = events[1:3]
    assert [event["event"] for event in events] == ["download", "arrival", "reject", "failure"]
    assert (arrival["server_version"], arrival["model_start_version"], arrival["staleness"]) == (
        0,
        0,
        0,
    )
    assert (reject["server_version"], reject["model_start_version"], reject["staleness"]) == (
        0,
        0,
        0,
    )
    assert "Invalid update tensor" in reject["reason"]
    assert server.version == 0
    for name, tensor in before.items():
        assert torch.equal(tensor, model.state_dict()[name])


def test_unreadable_upload_is_logged_without_accepting_update(tmp_path):
    from src.b0 import run_async

    server = AsyncServer(torch.nn.Linear(2, 1), total_samples=2)
    bad_payload = b"not a torch message"

    def unreadable_train(payload, local_data, model_config, cpu_threads):
        return bad_payload, 0.0

    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(ValueError, match="Invalid serialized payload"):
            run_async(
                server,
                {"client_0": (np.zeros((2, 2)), np.array([0, 1]))},
                {},
                {"seed": 42, "max_accepted_updates": 1, "max_concurrency": 1, "cpu_threads": 1},
                tmp_path,
                executor=executor,
                train_fn=unreadable_train,
            )
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == ["download", "reject", "failure"]
    assert events[1]["upload_bytes"] == len(bad_payload)
    assert events[1]["cumulative_total_bytes"] == events[0]["download_bytes"] + len(bad_payload)
    assert server.version == 0


def test_worker_failure_is_logged_and_not_applied(tmp_path):
    from src.b0 import run_async

    server = AsyncServer(torch.nn.Linear(2, 1), total_samples=2)

    def failed(*args):
        raise RuntimeError("controlled worker failure")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with pytest.raises(RuntimeError, match="controlled worker failure"):
            run_async(
                server,
                {"client_0": (np.zeros((2, 2)), np.array([0, 1]))},
                {},
                {"seed": 42, "max_accepted_updates": 1, "max_concurrency": 1, "cpu_threads": 1},
                tmp_path,
                executor=executor,
                train_fn=failed,
            )
    assert server.version == 0
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "failure"
    assert "controlled worker failure" in events[-1]["error"]


@pytest.fixture
def b0_experiment(experiment, tmp_path):
    config_path, config, sources = experiment
    pp.preprocess(config_path)
    part.freeze_partitions(config["preprocessing_manifest"], tmp_path / "partitions", 2, 10.0, 42)
    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "type": "mlp",
                    "hidden_dims": [8, 4],
                    "dropout": 0.2,
                    "task": "binary",
                    "precision": "fp32",
                },
                "training": {
                    "optimizer": "adam",
                    "learning_rate": 0.001,
                    "batch_size": 8,
                    "local_epochs": 1,
                    "seed": 42,
                },
            }
        )
    )
    fl_path = tmp_path / "async.yaml"
    fl_path.write_text(
        yaml.safe_dump(
            {
                "fl": {
                    "mode": "asynchronous",
                    "num_clients": 2,
                    "max_concurrency": 2,
                    "aggregation": "weighted_delta",
                    "staleness_weighting": "fixed",
                    "evaluation_every_accepted_updates": 2,
                    "checkpoint_every_accepted_updates": 2,
                }
            }
        )
    )
    pilot = {
        "seed": 42,
        "cpu_threads": 1,
        "max_accepted_updates": 4,
        "server_learning_rate": 1.0,
        "fixed_staleness_multiplier": 1.0,
        "preprocessing_manifest": config["preprocessing_manifest"],
        "partition_manifest": str(tmp_path / "partitions/partition_alpha10_seed42_manifest.json"),
        "model_config": str(model_path),
        "fl_config": str(fl_path),
        "policy_config": "configs/experiments.yaml",
        "run_dir": str(tmp_path / "b0_run"),
        "summary_output": str(tmp_path / "b0_summary.json"),
    }
    pilot_path = tmp_path / "pilot.yaml"
    pilot_path.write_text(yaml.safe_dump(pilot))
    return pilot_path, pilot, sources


def test_b0_process_pilot_without_test_csv_and_exact_replay(b0_experiment):
    from pathlib import Path

    from src.b0 import replay, run_b0

    config_path, config, sources = b0_experiment
    sources["test"].unlink()
    summary = run_b0(config_path)
    assert summary["status"] == "completed"
    assert summary["accepted_updates"] == 4
    assert summary["schema_version"] == 3
    assert summary["staleness_summary"]["run"]["count"] == 4
    assert sum(stats["count"] for stats in summary["staleness_summary"]["clients"].values()) == 4
    assert summary["policy"]["update_budget"] == 1.0
    assert [v["server_version"] for v in summary["validation_curve"]] == [0, 2, 4]
    assert sum(summary["client_updates"].values()) == 4
    assert summary["total_communicated_bytes"] == (
        summary["serialized_download_bytes"] + summary["serialized_upload_bytes"]
    )
    assert summary["serialized_download_overhead_bytes"] > 0
    assert summary["serialized_upload_overhead_bytes"] > 0
    cumulative = [item["cumulative_total_bytes"] for item in summary["validation_curve"]]
    assert cumulative[0] == 0
    assert cumulative == sorted(cumulative)
    assert cumulative[-1] == summary["total_communicated_bytes"]
    events = [
        json.loads(line)
        for line in (Path(config["run_dir"]) / "events.jsonl").read_text().splitlines()
    ]
    transfers = [event for event in events if event["event"] in ("download", "arrival")]
    for event in transfers:
        payload = (Path(config["run_dir"]) / event["payload_file"]).read_bytes()
        direction = "download_bytes" if event["event"] == "download" else "upload_bytes"
        assert event[direction] == event["payload_bytes"] == len(payload)
        assert event["frame_bytes"] == 0
        assert event["tensor_value_bytes"] + event["serialization_overhead_bytes"] == len(payload)
        assert event["serialization_seconds"] >= 0
        assert event["transfer_seconds"] is None
        assert event["transfer_timing_status"] == "unmeasured_process_pool_ipc"
    for reference in summary["artifacts"].values():
        pp.verify_ref(reference)
    sources["train"].unlink()  # Arrival replay depends only on the captured payloads.
    receipt = replay(config["run_dir"])
    assert receipt["final_model_matches"] is True
    assert receipt["staleness_summary"] == summary["staleness_summary"]
    assert receipt["total_communicated_bytes"] == summary["total_communicated_bytes"]
    assert (
        receipt["serialized_download_overhead_bytes"]
        == summary["serialized_download_overhead_bytes"]
    )
    assert (
        receipt["serialized_upload_overhead_bytes"] == summary["serialized_upload_overhead_bytes"]
    )
    before = Path(config["summary_output"]).read_bytes()
    with pytest.raises(FileExistsError):
        run_b0(config_path)
    assert Path(config["summary_output"]).read_bytes() == before
    log = Path(config["run_dir"]) / "events.jsonl"
    manifest_path = Path(config["run_dir"]) / "manifest.json"
    validation_path = Path(config["run_dir"]) / "validation.json"
    original_log, original_manifest = log.read_text(), manifest_path.read_text()
    original_validation = validation_path.read_text()
    legacy_events = [json.loads(line) for line in original_log.splitlines()]
    accounting_fields = (
        "payload_bytes",
        "frame_bytes",
        "tensor_value_bytes",
        "serialization_overhead_bytes",
        "serialization_seconds",
        "transfer_seconds",
        "transfer_timing_status",
        "cumulative_total_bytes",
    )
    for event in legacy_events:
        if event["event"] in ("download", "arrival"):
            for field in accounting_fields:
                event.pop(field)
    log.write_text("".join(json.dumps(event) + "\n" for event in legacy_events))
    legacy_curve = pp.read_json(validation_path)
    for observation in legacy_curve:
        observation.pop("cumulative_total_bytes")
    validation_path.write_text(json.dumps(legacy_curve))
    legacy_manifest = pp.read_json(manifest_path)
    legacy_manifest["schema_version"] = 2
    legacy_manifest["validation_curve"] = legacy_curve
    legacy_manifest["artifacts"]["events"] = pp.artifact_ref(log)
    legacy_manifest["artifacts"]["validation"] = pp.artifact_ref(validation_path)
    manifest_path.write_text(json.dumps(legacy_manifest))
    assert replay(config["run_dir"])["final_model_matches"] is True
    log.write_text(original_log)
    validation_path.write_text(original_validation)
    manifest_path.write_text(original_manifest)
    events = [json.loads(line) for line in original_log.splitlines()]
    first_arrival = next(event for event in events if event["event"] == "arrival")
    first_arrival["server_version"] += 1
    first_arrival["staleness"] += 1
    log.write_text("".join(json.dumps(event) + "\n" for event in events))
    manifest = pp.read_json(manifest_path)
    manifest["artifacts"]["events"] = pp.artifact_ref(log)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Replay arrival version mismatch"):
        replay(config["run_dir"])
    log.write_text(original_log)
    manifest_path.write_text(original_manifest)
    events = [json.loads(line) for line in original_log.splitlines()]
    first_download = next(event for event in events if event["event"] == "download")
    first_download["serialization_overhead_bytes"] += 1
    log.write_text("".join(json.dumps(event) + "\n" for event in events))
    manifest = pp.read_json(manifest_path)
    manifest["artifacts"]["events"] = pp.artifact_ref(log)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Replay message byte breakdown mismatch"):
        replay(config["run_dir"])
    log.write_text(original_log)
    manifest_path.write_text(original_manifest)
    log.write_text(log.read_text() + "{}\n")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        replay(config["run_dir"])


def test_b0_rejects_invalid_partition_before_creating_run(b0_experiment):
    from pathlib import Path

    from src.b0 import run_b0

    config_path, config, _ = b0_experiment
    manifest = pp.read_json(config["partition_manifest"])
    path = pp.verify_ref(manifest["artifacts"]["partition"])
    clients = pp.read_json(path)
    clients["client_0"][0] = clients["client_1"][0]
    path.write_text(json.dumps(clients))
    manifest["artifacts"]["partition"] = pp.artifact_ref(path)
    Path(config["partition_manifest"]).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="train-fit"):
        run_b0(config_path)
    assert not Path(config["run_dir"]).exists()


@pytest.mark.parametrize("invalid", ["stop", "seed", "concurrency", "budget", "demand", "epochs"])
def test_b0_rejects_invalid_or_adaptive_settings(b0_experiment, tmp_path, invalid):
    from pathlib import Path

    from src.b0 import run_b0

    path, config, _ = b0_experiment
    if invalid == "stop":
        config["max_accepted_updates"] = 0
    elif invalid == "seed":
        config["seed"] = 123
    elif invalid == "concurrency":
        fl = pp.read_config(config["fl_config"])
        fl["fl"]["max_concurrency"] = 3
        Path(config["fl_config"]).write_text(yaml.safe_dump(fl))
    elif invalid in ("budget", "demand"):
        policy = pp.read_config(config["policy_config"])
        policy["policies"]["B0"]["update_budget" if invalid == "budget" else "demand_budget"] = (
            0.5 if invalid == "budget" else True
        )
        policy_path = tmp_path / "policy.yaml"
        policy_path.write_text(yaml.safe_dump(policy))
        config["policy_config"] = str(policy_path)
    else:
        model = pp.read_config(config["model_config"])
        model["training"]["local_epochs"] = 0
        Path(config["model_config"]).write_text(yaml.safe_dump(model))
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        run_b0(path)
    assert not Path(config["run_dir"]).exists()
