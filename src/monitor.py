"""Offline, prefix-causal client observations from frozen B0 event logs."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from src.preprocess import artifact_ref, read_json, verify_ref, write_json

UNITS = {
    "num_samples": "samples",
    "previous_local_train_seconds": "seconds",
    "rtt_seconds": "seconds",
    "throughput_bytes_per_second": "bytes/second",
    "last_arrival_staleness": "server_versions",
    "contribution_age_seconds": "seconds",
}
IDENTITY = ("client_id", "model_start_version", "training_seed")


def _seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _source(artifact, fields, index=0, event=None):
    return {
        "artifact": artifact,
        "event_index": index,
        "event": event["event"] if event else None,
        "job_id": event.get("job_id") if event else None,
        "fields": fields,
    }


def _field(name, value, status, source=(), time=None):
    return {
        "value": value,
        "unit": UNITS[name],
        "status": status,
        "source": list(source),
        "observed_at": time,
        "available_at": time,
    }


class StateMonitor:
    """Consume one event at a time; never inspect future events or a live model."""

    def __init__(self, client_counts, *, run_id):
        if (
            not isinstance(client_counts, dict)
            or not client_counts
            or any(
                not isinstance(client, str) or not client or type(count) is not int or count <= 0
                for client, count in client_counts.items()
            )
        ):
            raise ValueError("Invalid client sample counts")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Invalid run identity")
        self.run_id = run_id
        self.counts = dict(sorted(client_counts.items()))
        self.index = 0
        self.elapsed = 0.0
        self.version = 0
        self.jobs = {}
        self.seen = set()
        self.pending_arrival = None
        self.rejected = False
        self.failed = False
        self.latest = {client: {} for client in self.counts}
        self.last_apply = {}
        self.clock_source = None
        self.issues = []

    def consume(self, event):
        """Validate before mutating state. Returned snapshots are detached copies."""
        if not isinstance(event, dict):
            raise ValueError("Event must be an object")
        kind = event.get("event")
        elapsed = event.get("elapsed_seconds")
        if not _seconds(elapsed) or elapsed < self.elapsed:
            raise ValueError("Invalid/decreasing event time")
        if self.failed or (self.rejected and kind != "failure"):
            raise ValueError("Event after rejection/failure")
        if self.pending_arrival and kind not in ("apply", "reject"):
            raise ValueError("Arrival must be followed by apply or reject")
        if kind == "failure":
            if (
                type(event.get("server_version")) is not int
                or event["server_version"] != self.version
            ):
                raise ValueError("Failure version mismatch")
        elif kind in ("download", "arrival", "apply", "reject"):
            self._validate_job(event)
        else:
            raise ValueError("Unknown event kind")

        self.index += 1
        self.elapsed = float(elapsed)
        self.clock_source = _source("events", ["elapsed_seconds"], self.index, event)
        time = {"event_index": self.index, "elapsed_seconds": self.elapsed}
        if kind == "failure":
            self.failed = True
            return
        client, job = event["client_id"], event["job_id"]
        if kind == "download":
            self.jobs[job] = {key: event[key] for key in IDENTITY}
            self.seen.add(job)
        elif kind == "arrival":
            self.pending_arrival = job
            duration = event.get("local_train_seconds")
            status = (
                "missing_observation"
                if duration is None
                else "observed"
                if _seconds(duration)
                else "invalid_observation"
            )
            self.latest[client]["previous_local_train_seconds"] = _field(
                "previous_local_train_seconds",
                float(duration) if status == "observed" else None,
                status,
                [_source("events", ["local_train_seconds"], self.index, event)],
                time,
            )
            if status != "observed":
                self.issues.append(
                    {
                        "client_id": client,
                        "event_index": self.index,
                        "field": "previous_local_train_seconds",
                        "status": status,
                    }
                )
            self.latest[client]["last_arrival_staleness"] = _field(
                "last_arrival_staleness",
                event["staleness"],
                "observed",
                [
                    _source(
                        "events",
                        ["server_version", "model_start_version", "staleness"],
                        self.index,
                        event,
                    )
                ],
                time,
            )
        else:
            if kind == "apply":
                self.version += 1
                self.last_apply[client] = (self.elapsed, self.clock_source)
            else:
                self.rejected = True
            self.pending_arrival = None
            del self.jobs[job]

    def _validate_job(self, event):
        kind, client, job = event["event"], event.get("client_id"), event.get("job_id")
        if not isinstance(client, str) or client not in self.counts:
            raise ValueError("Unknown client")
        if not isinstance(job, str) or not job:
            raise ValueError("Invalid job identity")
        for key in ("model_start_version", "training_seed"):
            if type(event.get(key)) is not int or event[key] < 0:
                raise ValueError(f"Invalid {key}")
        if kind in ("download", "apply") and (
            type(event.get("num_samples")) is not int or event["num_samples"] != self.counts[client]
        ):
            raise ValueError("Client sample count mismatch")
        if kind == "download":
            if job in self.seen or any(
                active["client_id"] == client for active in self.jobs.values()
            ):
                raise ValueError("Duplicate job or busy client")
            if event["model_start_version"] != self.version:
                raise ValueError("Download version mismatch")
            return
        if job not in self.jobs or any(event[key] != self.jobs[job][key] for key in IDENTITY):
            raise ValueError("Unmatched job identity")
        if self.pending_arrival is not None and self.pending_arrival != job:
            raise ValueError("Unmatched arrival receipt")
        version_key = "version_before" if kind == "apply" else "server_version"
        lag = self.version - event["model_start_version"]
        if (
            type(event.get(version_key)) is not int
            or event[version_key] != self.version
            or type(event.get("staleness")) is not int
            or event["staleness"] != lag
            or lag < 0
        ):
            raise ValueError("Event version/staleness mismatch")
        if kind == "apply" and (
            self.pending_arrival != job
            or type(event.get("version_after")) is not int
            or event["version_after"] != self.version + 1
        ):
            raise ValueError("Apply without arrival or invalid next version")

    def snapshot(self):
        time = {"event_index": self.index, "elapsed_seconds": self.elapsed}
        rows = []
        for client, count in self.counts.items():
            fields = {
                "num_samples": _field(
                    "num_samples",
                    count,
                    "static_metadata",
                    [_source("partition", [f"clients.{client}.row_count"])],
                    {"event_index": 0, "elapsed_seconds": 0.0},
                ),
            }
            for name in ("rtt_seconds", "throughput_bytes_per_second"):
                fields[name] = _field(
                    name,
                    None,
                    "unmeasured_process_pool_ipc",
                    [
                        _source("configuration", ["byte_accounting.transfer_timing"]),
                    ],
                )
            for name in ("previous_local_train_seconds", "last_arrival_staleness"):
                fields[name] = self.latest[client].get(
                    name,
                    _field(name, None, "not_yet_observed"),
                )
            if client in self.last_apply:
                elapsed, source = self.last_apply[client]
                fields["contribution_age_seconds"] = _field(
                    "contribution_age_seconds",
                    self.elapsed - elapsed,
                    "derived",
                    [source, self.clock_source],
                    time,
                )
            else:
                fields["contribution_age_seconds"] = _field(
                    "contribution_age_seconds",
                    None,
                    "never_contributed",
                )
            rows.append(
                {
                    "schema_version": 1,
                    "run_id": self.run_id,
                    "client_id": client,
                    "through_event_index": self.index,
                    "observation_elapsed_seconds": self.elapsed,
                    "server_version": self.version,
                    "fields": fields,
                }
            )
        return copy.deepcopy(rows)


def _prepare_run(run_dir):
    """Check immutable inputs; use existing B0 replay only as an audit receipt."""
    import torch

    from src.b0 import replay

    run_dir = Path(run_dir).resolve()
    summary = read_json(run_dir / "manifest.json")
    if (
        summary.get("schema_version") != 3
        or summary.get("status") != "completed"
        or summary.get("policy", {}).get("update_budget") != 1.0
    ):
        raise ValueError("Monitoring requires a completed schema-3 full-budget B0 run")
    config_ref = summary["artifacts"]["configuration"]
    config = read_json(verify_ref(config_ref))
    if config.get("byte_accounting", {}).get("transfer_timing") != "unmeasured_process_pool_ipc":
        raise ValueError("Unsupported B0 timing contract")
    for refs in (config["source_files"], config["configuration_sources"]):
        for reference in refs.values():
            verify_ref(reference)
    partition = read_json(verify_ref(config["partition_manifest"]))
    if (
        partition["partition_scope"] != "train_fit_only"
        or partition["preprocessing_manifest"] != config["preprocessing_manifest"]
        or partition["dataset_manifest"] != config["dataset_manifest"]
        or partition["artifacts"]["partition"]["sha256"] != config["partition_sha256"]
        or summary["partition_sha256"] != config["partition_sha256"]
    ):
        raise ValueError("Partition/configuration linkage mismatch")
    allocated = read_json(verify_ref(partition["artifacts"]["partition"]))
    counts = {client: record["row_count"] for client, record in partition["clients"].items()}
    StateMonitor(counts, run_id=str(run_dir))  # Validate before arithmetic or creating output.
    if (
        sorted(counts) != sorted(partition["client_ids"])
        or sorted(counts) != sorted(allocated)
        or sorted(counts) != sorted(summary["client_updates"])
        or any(count != len(allocated[client]) for client, count in counts.items())
        or sum(counts.values()) != config["total_train_fit"]
    ):
        raise ValueError("Partition client count mismatch")
    inputs = {
        "run_manifest": artifact_ref(run_dir / "manifest.json"),
        "configuration": config_ref,
        "partition": config["partition_manifest"],
        "partition_rows": partition["artifacts"]["partition"],
        "events": summary["artifacts"]["events"],
    }
    for reference in inputs.values():
        verify_ref(reference)
    # B0 replay initializes a temporary model; restore the caller's CPU RNG.
    with torch.random.fork_rng(devices=[]):
        receipt = replay(run_dir)
    return counts, {
        "schema_version": 1,
        "run_id": str(run_dir),
        "observation_scope": "offline_event_prefix",
        "clock": "b0_log_elapsed_seconds_then_event_index",
        "inputs": inputs,
        "monitor_source": artifact_ref(__file__),
        "schema": artifact_ref(Path(__file__).resolve().parents[1] / "tasks/day8-state-schema.md"),
        "b0_replay": receipt,
    }


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def _render_snapshots(counts, report, stream=None):
    """Stream rows or compute their hash without writing anything during verify."""
    state = StateMonitor(counts, run_id=report["run_id"])
    digest = hashlib.sha256()
    status_counts = {name: {} for name in UNITS}
    row_count = 0

    def emit():
        nonlocal row_count
        for row in state.snapshot():
            payload = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            digest.update(payload)
            if stream is not None:
                stream.write(payload)
            row_count += 1
            for name, field in row["fields"].items():
                status = field["status"]
                status_counts[name][status] = status_counts[name].get(status, 0) + 1

    emit()
    with verify_ref(report["inputs"]["events"]).open(encoding="utf-8") as events:
        for line in events:
            state.consume(json.loads(line, parse_constant=_invalid_constant))
            emit()
    if (
        state.jobs
        or state.failed
        or state.rejected
        or state.version != report["b0_replay"]["accepted_updates"]
    ):
        raise ValueError("Monitoring trace is not a drained completed B0 run")
    report.update(
        event_count=state.index,
        snapshot_count=row_count,
        client_ids=list(state.counts),
        status_counts=status_counts,
        observation_issues=state.issues,
    )
    return digest.hexdigest()


def replay_monitor(run_dir, output_dir):
    """Create independent monitoring evidence, never edit a source run."""
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).resolve()
    if output_dir == run_dir or run_dir in output_dir.parents:
        raise ValueError("Monitoring output must be outside the B0 run")
    if output_dir.exists():
        raise FileExistsError("Monitoring output already exists; choose a fresh directory")
    counts, report = _prepare_run(run_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    path = output_dir / "snapshots.jsonl"
    with path.open("xb") as stream:
        digest = _render_snapshots(counts, report, stream)
    report["snapshots"] = {"path": str(path), "sha256": digest}
    # Detect changed inputs during generation before certifying a bundle.
    for reference in report["inputs"].values():
        verify_ref(reference)
    write_json(output_dir / "manifest.json", report)
    return report


def verify_monitor(manifest):
    """Recompute snapshot bytes and report content from verified source inputs."""
    saved = read_json(manifest)
    for key in ("monitor_source", "schema", "snapshots"):
        verify_ref(saved[key])
    for reference in saved["inputs"].values():
        verify_ref(reference)
    counts, expected = _prepare_run(saved["run_id"])
    digest = _render_snapshots(counts, expected)
    if digest != saved["snapshots"]["sha256"]:
        raise ValueError("Monitoring snapshot content differs from event replay")
    expected["snapshots"] = saved["snapshots"]
    if expected != saved:
        raise ValueError("Monitoring manifest differs from current evidence")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("replay", help="Create a separate B0 monitoring bundle")
    generate.add_argument("--run-dir", required=True)
    generate.add_argument("--output-dir", required=True)
    verify = commands.add_parser("verify", help="Recompute and verify a monitoring bundle")
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.command == "replay":
        result = replay_monitor(args.run_dir, args.output_dir)
        status = "created"
    else:
        result = verify_monitor(args.manifest)
        status = "verified"
    print(json.dumps({"status": status, "snapshot_count": result["snapshot_count"]}))


if __name__ == "__main__":
    main()
