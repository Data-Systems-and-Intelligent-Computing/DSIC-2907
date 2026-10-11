"""Controlled Day 6 update-budget probe from one previously trained B0 delta."""

import argparse
import json
import time
from pathlib import Path

import torch

from src.async_server import AsyncServer
from src.centralized import build_model
from src.client import deserialize_message, serialize_message
from src.compressor import (
    BUDGETS,
    FORMAT_VERSION,
    OPERATOR,
    decode_update,
    encode_update,
    measure_budget_upload,
)
from src.preprocess import artifact_ref, read_json, write_json


def run_probe(source_dir, output, payload_dir, job_id="job_0000"):
    """Compare three serialized uploads from exactly one saved full delta."""
    source_dir, output, payload_dir = Path(source_dir), Path(output), Path(payload_dir)
    if output.exists() or payload_dir.exists():
        raise FileExistsError("Day 6 report/payload path already exists")
    upload_path = source_dir / "messages" / f"{job_id}_upload.pt"
    download_path = source_dir / "messages" / f"{job_id}_download.pt"
    upload_bytes, download_bytes = upload_path.read_bytes(), download_path.read_bytes()
    update, download = deserialize_message(upload_bytes), deserialize_message(download_bytes)
    for key in ("job_id", "client_id", "model_start_version"):
        if update[key] != download[key]:
            raise ValueError(f"Source upload/download {key} mismatch")
    if update["job_id"] != job_id or update["budget"] != 1.0:
        raise ValueError("Probe requires the selected full-budget job")
    state = download["model_state"]
    decode_update(update, state)
    configuration = read_json(source_dir / "configuration.json")
    settings = configuration["pilot_settings"]
    arrival_serialization_seconds = None
    events_path = source_dir / "events.jsonl"
    if events_path.is_file():
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        arrivals = [
            event for event in events if event["event"] == "arrival" and event["job_id"] == job_id
        ]
        downloads = [
            event for event in events if event["event"] == "download" and event["job_id"] == job_id
        ]
        if len(arrivals) != 1 or len(downloads) != 1:
            raise ValueError("Source job events are missing or duplicated")
        if arrivals[0]["payload_sha256"] != artifact_ref(upload_path)["sha256"] or (
            downloads[0]["payload_sha256"] != artifact_ref(download_path)["sha256"]
        ):
            raise ValueError("Saved source message hash differs from event log")
        arrival_serialization_seconds = arrivals[0]["serialization_seconds"]
    report = {
        "schema_version": 1,
        "operator": OPERATOR,
        "sparse_format_version": FORMAT_VERSION,
        "byte_boundary": "serialized_application_message",
        "application_frame_bytes": 0,
        "private_process_pool_ipc_bytes": None,
        "source": {
            "job_id": job_id,
            "upload": artifact_ref(upload_path),
            "download": artifact_ref(download_path),
            "configuration": artifact_ref(source_dir / "configuration.json"),
            "events": artifact_ref(events_path) if events_path.is_file() else None,
            "local_train_seconds": update.get("local_train_seconds"),
        },
        "download_bytes": len(download_bytes),
        "actions": {},
    }
    payloads = {}
    for budget in BUDGETS:
        label = f"{budget:.2f}"
        if budget == 1.0:
            wire, payload = update, upload_bytes
            compression_seconds = 0.0
            serialization_seconds = arrival_serialization_seconds
        else:
            started = time.perf_counter()
            wire = encode_update(update, budget)
            compression_seconds = time.perf_counter() - started
            started = time.perf_counter()
            payload = serialize_message(wire)
            serialization_seconds = time.perf_counter() - started
        decoded = decode_update(deserialize_message(payload), state)
        model = build_model(configuration["n_features"], configuration["local_training"])
        model.load_state_dict(state, strict=True)
        server = AsyncServer(
            model,
            configuration["total_train_fit"],
            settings["server_learning_rate"],
            settings["fixed_staleness_multiplier"],
            allowed_budgets=BUDGETS,
        )
        server.version = download["model_start_version"]
        receipt = server.apply_update(decoded, download["model_start_version"])
        for name, before in state.items():
            expected = before + decoded["delta"][name] * receipt["weight"]
            torch.testing.assert_close(model.state_dict()[name], expected)
        if receipt["version_after"] != download["model_start_version"] + 1:
            raise ValueError("Probe server version did not advance exactly once")
        counts = {
            name: {
                "retained": wire["sparse_delta"][name]["count"] if budget < 1.0 else tensor.numel(),
                "total": tensor.numel(),
            }
            for name, tensor in update["delta"].items()
        }
        measured = measure_budget_upload(payload, wire)
        filename = f"{job_id}_budget_{label}_upload.pt"
        payloads[filename] = payload
        report["actions"][label] = {
            "budget": budget,
            "per_tensor_entries": counts,
            "retained_parameters": sum(item["retained"] for item in counts.values()),
            "total_parameters": sum(item["total"] for item in counts.values()),
            "upload": measured,
            "total_bytes": measured["payload_bytes"] + len(download_bytes),
            "compression_seconds": compression_seconds,
            "serialization_seconds": serialization_seconds,
            "serialization_timing_source": (
                "saved_day5_arrival" if budget == 1.0 else "day6_probe"
            ),
            "model_effect_verified": True,
            "server_receipt": receipt,
        }
    baseline = report["actions"]["1.00"]
    for result in report["actions"].values():
        result["saved_upload_bytes"] = (
            baseline["upload"]["payload_bytes"] - result["upload"]["payload_bytes"]
        )
        result["saved_total_bytes"] = baseline["total_bytes"] - result["total_bytes"]
        result["saved_total_percent"] = 100 * result["saved_total_bytes"] / baseline["total_bytes"]
    payload_dir.mkdir(parents=True, exist_ok=False)
    for label, result in report["actions"].items():
        filename = f"{job_id}_budget_{label}_upload.pt"
        path = payload_dir / filename
        with path.open("xb") as stream:
            stream.write(payloads[filename])
        result["payload"] = artifact_ref(path)
    write_json(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--payload-dir", required=True)
    parser.add_argument("--job-id", default="job_0000")
    args = parser.parse_args()
    report = run_probe(args.source_dir, args.output, args.payload_dir, args.job_id)
    for label, result in report["actions"].items():
        print(label, result["upload"]["payload_bytes"], result["saved_total_bytes"])


if __name__ == "__main__":
    main()
