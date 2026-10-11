"""Create and verify the Week 1 B0 backbone freeze from saved pilot evidence."""

import argparse
import json
from pathlib import Path

import torch

from src.b0 import replay
from src.client import deserialize_message
from src.compressor import (
    BUDGETS,
    FORMAT_VERSION,
    OPERATOR,
    decode_update,
    measure_budget_upload,
)
from src.preprocess import artifact_ref, read_json, verify_ref, write_json


def normalized_snapshot(snapshot):
    """Remove only run destinations and incidental Git status from a B0 snapshot."""
    settings = {
        key: value
        for key, value in snapshot["pilot_settings"].items()
        if key not in ("run_dir", "summary_output")
    }
    return {
        **{
            key: value
            for key, value in snapshot.items()
            if key not in ("pilot_settings", "pilot_configuration", "git")
        },
        "pilot_settings": settings,
    }


def event_schema(path):
    """Record the field names and JSON types of each completed B0 event kind."""
    schema = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            raise ValueError("Invalid event schema record")
        fields = {
            key: "null" if value is None else type(value).__name__
            for key, value in sorted(event.items())
        }
        kind = event["event"]
        if kind in schema and schema[kind] != fields:
            raise ValueError(f"Inconsistent event schema: {kind}")
        schema[kind] = fields
    if not schema:
        raise ValueError("Empty event schema")
    return dict(sorted(schema.items()))


def _verify_budget_probe(reference):
    report = read_json(verify_ref(reference))
    if (
        report.get("operator") != OPERATOR
        or report.get("sparse_format_version") != FORMAT_VERSION
        or set(report.get("actions", {})) != {f"{q:.2f}" for q in BUDGETS}
    ):
        raise ValueError("Day 6 budget probe contract mismatch")
    for source in ("upload", "download", "configuration", "events"):
        verify_ref(report["source"][source])
    download = verify_ref(report["source"]["download"]).read_bytes()
    state = deserialize_message(download)["model_state"]
    if report["download_bytes"] != len(download):
        raise ValueError("Day 6 download byte count mismatch")
    for label, action in report["actions"].items():
        payload = verify_ref(action["payload"]).read_bytes()
        wire = deserialize_message(payload)
        decoded = decode_update(wire, state)
        if (
            decoded["budget"] != action["budget"]
            or f"{decoded['budget']:.2f}" != label
            or action["upload"] != measure_budget_upload(payload, wire)
            or action["total_bytes"] != len(payload) + len(download)
            or action["model_effect_verified"] is not True
        ):
            raise ValueError(f"Day 6 budget evidence mismatch: {label}")
    baseline = report["actions"]["1.00"]["total_bytes"]
    for action in report["actions"].values():
        if action["saved_total_bytes"] != baseline - action["total_bytes"]:
            raise ValueError("Day 6 signed byte savings mismatch")
    return report


def collect_freeze(run_dirs, budget_report):
    """Recompute the freeze contract from two independent completed B0 runs."""
    if len(run_dirs) != 2 or Path(run_dirs[0]).resolve() == Path(run_dirs[1]).resolve():
        raise ValueError("Two distinct B0 repeat runs are required")
    budget_ref = artifact_ref(budget_report)
    _verify_budget_probe(budget_ref)
    runs, snapshots, schemas, initials = [], [], [], []
    for run_dir in map(lambda path: Path(path).resolve(), run_dirs):
        manifest_path = run_dir / "manifest.json"
        summary = read_json(manifest_path)
        if (
            summary.get("schema_version") != 3
            or summary.get("status") != "completed"
            or summary.get("policy", {}).get("update_budget") != 1.0
        ):
            raise ValueError("Freeze requires completed full-budget B0 schema-3 runs")
        snapshot = read_json(verify_ref(summary["artifacts"]["configuration"]))
        if summary["accepted_updates"] != snapshot["pilot_settings"]["max_accepted_updates"]:
            raise ValueError("B0 accepted-update count differs from its configuration")
        for reference in snapshot["source_files"].values():
            verify_ref(reference)
        for reference in snapshot["configuration_sources"].values():
            verify_ref(reference)
        for key in ("preprocessing_manifest", "partition_manifest", "dataset_manifest"):
            verify_ref(snapshot[key])
        summary_output = Path(snapshot["pilot_settings"]["summary_output"])
        if read_json(summary_output) != summary:
            raise ValueError("B0 processed summary differs from raw manifest")
        receipt_path = summary_output.with_name(summary_output.stem + "_replay.json")
        actual_replay = replay(run_dir)
        if read_json(receipt_path) != actual_replay or not actual_replay["final_model_matches"]:
            raise ValueError("B0 replay receipt differs from saved messages")
        for reference in summary["artifacts"].values():
            verify_ref(reference)
        for reference in summary["checkpoints"]:
            verify_ref(reference)
        schema = event_schema(run_dir / "events.jsonl")
        if set(schema) != {"download", "arrival", "apply"}:
            raise ValueError("Completed B0 event kinds differ from the freeze baseline")
        initial = torch.load(
            verify_ref(summary["artifacts"]["initial_model"]),
            map_location="cpu",
            weights_only=True,
        )["model_state"]
        runs.append(
            {
                "run_dir": str(run_dir),
                "manifest": artifact_ref(manifest_path),
                "configuration_snapshot": summary["artifacts"]["configuration"],
                "pilot_configuration": snapshot["pilot_configuration"],
                "summary": artifact_ref(summary_output),
                "replay_receipt": artifact_ref(receipt_path),
                "accepted_updates": summary["accepted_updates"],
                "serialized_download_bytes": actual_replay["serialized_download_bytes"],
                "serialized_upload_bytes": actual_replay["serialized_upload_bytes"],
                "total_communicated_bytes": actual_replay["total_communicated_bytes"],
                "maximum_staleness": actual_replay["staleness_summary"]["run"]["maximum"],
                "final_model_sha256": actual_replay["final_model_sha256"],
            }
        )
        snapshots.append(snapshot)
        schemas.append(schema)
        initials.append(initial)
    contract_a, contract_b = (normalized_snapshot(snapshot) for snapshot in snapshots)
    if contract_a != contract_b:
        raise ValueError("B0 repeat runs differ in frozen configuration or source hashes")
    if schemas[0] != schemas[1]:
        raise ValueError("B0 repeat event schemas differ")
    if set(initials[0]) != set(initials[1]) or any(
        not torch.equal(initials[0][name], initials[1][name]) for name in initials[0]
    ):
        raise ValueError("B0 repeat initial model tensors differ")
    if any(
        run[key] != runs[0][key]
        for run in runs[1:]
        for key in ("accepted_updates", "serialized_download_bytes", "serialized_upload_bytes")
    ):
        raise ValueError("B0 repeat counts or serialized bytes differ")
    preprocessing = read_json(verify_ref(snapshots[0]["preprocessing_manifest"]))
    feature_names = preprocessing["artifacts"]["feature_names"]
    pipeline = preprocessing["artifacts"]["pipeline"]
    verify_ref(feature_names)
    verify_ref(pipeline)
    source_dir = Path(__file__).resolve().parent
    return {
        "schema_version": 1,
        "scope": "week1_cpu_b0_backbone_not_day14_main_protocol",
        "configuration": contract_a,
        "feature_order": feature_names,
        "preprocessing_pipeline": pipeline,
        "serialization": {
            "format": "torch.save_application_message",
            "boundary": "serialized_application_message",
            "application_frame_bytes": 0,
            "client_source": snapshots[0]["source_files"]["client.py"],
        },
        "update_operator": {
            "name": OPERATOR,
            "budgets": list(BUDGETS),
            "sparse_format_version": FORMAT_VERSION,
            "source": artifact_ref(source_dir / "compressor.py"),
            "probe_source": artifact_ref(source_dir / "budget_probe.py"),
            "day6_report": budget_ref,
        },
        "evaluation": {
            "positive_class": "Attack=1",
            "threshold": contract_a["threshold"],
            "metric_names": sorted(
                read_json(Path(runs[0]["run_dir"]) / "manifest.json")["validation_curve"][0][
                    "metrics"
                ]
            ),
            "metric_source": snapshots[0]["source_files"]["metrics.py"],
            "official_test_evaluated": False,
        },
        "baseline_event_log_schema": schemas[0],
        "runs": runs,
        "test_report": {
            "replays_match_saved_models": True,
            "same_configuration_and_source_hashes": True,
            "same_initial_model_tensors": True,
            "same_event_schema": True,
            "budget_probe_payloads_verified": True,
        },
        "main_protocol_pending": {
            "resource_limits_and_main_concurrency": "to_be_decided_at_pilot",
            "network_rtt_bandwidth_profiles": "to_be_decided_at_pilot",
            "demand_state_weights_and_thresholds": "Day_8_to_14",
            "participation_mapping_cooldown_fairness": "Day_8_to_14",
            "budget_policy_and_error_feedback": "Day_8_to_14",
            "macro_f1_target_and_main_stopping_rules": "Day_14_protocol_freeze",
            "analysis_plan": "Day_14_protocol_freeze",
        },
        "known_limitations": [
            "Two seed-42 CPU B0 pilots; not a multi-seed or B0-B3 result.",
            "Asynchronous completion order and final model bytes can differ between repeats.",
            "Private process-pool IPC bytes and transfer time are unmeasured.",
            "The sparse budget operator is only proven in a controlled probe, not B0 live runs.",
            "Source hashes pin a dirty working tree; Day 14 main protocol remains open.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--run-a", required=True)
    create.add_argument("--run-b", required=True)
    create.add_argument("--budget-report", required=True)
    create.add_argument("--output", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.command == "create":
        output = Path(args.output)
        if output.exists():
            raise FileExistsError("Week 1 freeze manifest already exists")
        report = collect_freeze((args.run_a, args.run_b), args.budget_report)
        write_json(output, report)
    else:
        saved = read_json(args.manifest)
        expected = collect_freeze(
            [run["run_dir"] for run in saved["runs"]],
            saved["update_operator"]["day6_report"]["path"],
        )
        if saved != expected:
            raise ValueError("Week 1 freeze manifest differs from current evidence")
    print(json.dumps({"status": "verified", "runs": 2, "schema_version": 1}))


if __name__ == "__main__":
    main()
