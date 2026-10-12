"""Offline, prefix-causal client observations from frozen B0 event logs."""

import copy
import math

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
