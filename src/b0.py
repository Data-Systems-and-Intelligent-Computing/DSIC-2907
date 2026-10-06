"""B0 CPU pilot: uniform idle-client dispatch and immediate completion-order apply."""

import argparse
import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from queue import Queue

import numpy as np
import torch

from src.async_server import AsyncServer
from src.centralized import build_model, git_metadata, predict
from src.client import deserialize_message, serialize_message, train_client
from src.metrics import THRESHOLD, binary_metrics
from src.preprocess import (
    artifact_ref,
    class_summary,
    features_target,
    load_preprocessing,
    load_source,
    package_versions,
    read_config,
    read_json,
    sha256,
    transform,
    verify_ref,
    write_json,
)


def run_async(
    server,
    client_data,
    model_config,
    settings,
    run_dir,
    on_apply=None,
    executor=None,
    train_fn=train_client,
):
    """Drain exactly the admitted job budget; one in-flight job per client.

    Completion callbacks enqueue arrivals in receipt order. Applying a completed
    update never waits for another client. A new eligible job is dispatched
    immediately after apply. Separate processes isolate local-training RNGs.
    """
    run_dir = Path(run_dir)
    messages = run_dir / "messages"
    messages.mkdir(exist_ok=False)
    active, events = {}, []
    arrivals = Queue()
    rng = np.random.Generator(np.random.PCG64(settings["seed"]))
    client_ids = sorted(client_data)
    launched = 0
    started = time.perf_counter()
    pool = (
        nullcontext(executor)
        if executor is not None
        else ProcessPoolExecutor(
            max_workers=settings["max_concurrency"],
            mp_context=multiprocessing.get_context("spawn"),
        )
    )
    with (run_dir / "events.jsonl").open("x", encoding="utf-8") as log, pool as workers:

        def record(event, **fields):
            entry = {"event": event, "elapsed_seconds": time.perf_counter() - started, **fields}
            log.write(json.dumps(entry, allow_nan=False, sort_keys=True) + "\n")
            log.flush()
            events.append(entry)

        def dispatch():
            nonlocal launched
            busy = {job["client_id"] for job in active.values()}
            eligible = [client for client in client_ids if client not in busy]
            client_id = eligible[int(rng.integers(len(eligible)))]
            job_id = f"job_{launched:04d}"
            training_seed = int(
                np.random.SeedSequence(
                    [settings["seed"], client_ids.index(client_id), launched]
                ).generate_state(1)[0]
            )
            job = {
                "job_id": job_id,
                "client_id": client_id,
                "model_start_version": server.version,
                "training_seed": training_seed,
            }
            payload = serialize_message({**job, "model_state": server.model.state_dict()})
            path = messages / f"{job_id}_download.pt"
            with path.open("xb") as stream:
                stream.write(payload)
            record(
                "download",
                **job,
                budget=1.0,
                num_samples=len(client_data[client_id][1]),
                download_bytes=len(payload),
                payload_file=str(path.relative_to(run_dir)),
                payload_sha256=sha256(path),
            )
            future = workers.submit(
                train_fn, payload, client_data[client_id], model_config, settings["cpu_threads"]
            )
            active[future] = job
            future.add_done_callback(
                lambda done: arrivals.put((done, time.perf_counter() - started))
            )
            launched += 1

        try:
            while launched < min(settings["max_concurrency"], settings["max_accepted_updates"]):
                dispatch()
            while active:
                future, arrival_time = arrivals.get()
                job = active.pop(future)
                payload = future.result()
                path = messages / f"{job['job_id']}_upload.pt"
                with path.open("xb") as stream:
                    stream.write(payload)
                update = deserialize_message(payload)
                if any(update[key] != value for key, value in job.items()):
                    raise ValueError("Worker update identity differs from its download")
                if update["num_samples"] != len(client_data[job["client_id"]][1]):
                    raise ValueError("Worker sample count differs from frozen client data")
                record(
                    "arrival",
                    **job,
                    arrival_elapsed_seconds=arrival_time,
                    server_version=server.version,
                    upload_bytes=len(payload),
                    payload_file=str(path.relative_to(run_dir)),
                    payload_sha256=sha256(path),
                    local_train_seconds=update["local_train_seconds"],
                    training_bce_by_epoch=update["training_bce_by_epoch"],
                )
                receipt = server.apply_update(update, job["model_start_version"])
                record(
                    "apply",
                    **job,
                    **receipt,
                    budget=update["budget"],
                    num_samples=update["num_samples"],
                )
                if on_apply is not None:
                    on_apply()
                if launched < settings["max_accepted_updates"]:
                    dispatch()
        except Exception as exc:
            record("failure", server_version=server.version, error=f"{type(exc).__name__}: {exc}")
            raise
    return {
        "events": events,
        "wall_clock_seconds": time.perf_counter() - started,
        "accepted_updates": server.version,
        "client_updates": {
            client: sum(e["event"] == "apply" and e["client_id"] == client for e in events)
            for client in client_ids
        },
        "serialized_download_bytes": sum(e.get("download_bytes", 0) for e in events),
        "serialized_upload_bytes": sum(e.get("upload_bytes", 0) for e in events),
    }


def load_inputs(config):
    """Verify the frozen data/partition linkage before providing any client data."""
    model_source = read_config(config["model_config"])
    fl = read_config(config["fl_config"])["fl"]
    policy = read_config(config["policy_config"])["policies"]["B0"]
    if policy["demand_participation"] or policy["demand_budget"] or policy["update_budget"] != 1.0:
        raise ValueError("B0 requires uniform participation and full update budget")
    if (fl["mode"], fl["aggregation"], fl["staleness_weighting"]) != (
        "asynchronous",
        "weighted_delta",
        "fixed",
    ):
        raise ValueError("Unsupported asynchronous backbone")
    for name, value in {
        "cpu_threads": config["cpu_threads"],
        "max_accepted_updates": config["max_accepted_updates"],
        **{
            key: fl[key]
            for key in (
                "num_clients",
                "max_concurrency",
                "evaluation_every_accepted_updates",
                "checkpoint_every_accepted_updates",
            )
        },
    }.items():
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if type(config["seed"]) is not int or config["seed"] < 0:
        raise ValueError("seed must be a nonnegative integer")
    if fl["max_concurrency"] > fl["num_clients"]:
        raise ValueError("Concurrency exceeds number of clients")
    model, training = model_source["model"], model_source["training"]
    if (model["type"], model["task"], model["precision"], training["optimizer"]) != (
        "mlp",
        "binary",
        "fp32",
        "adam",
    ):
        raise ValueError("B0 supports binary fp32 MLP with Adam only")
    local_config = {
        "hidden_dimensions": model["hidden_dims"],
        "dropout": model["dropout"],
        "epochs": training["local_epochs"],
        "batch_size": training["batch_size"],
        "optimizer": "Adam",
        "learning_rate": training["learning_rate"],
    }
    for key in ("epochs", "batch_size"):
        if type(local_config[key]) is not int or local_config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    if not np.isfinite(local_config["learning_rate"]) or local_config["learning_rate"] <= 0:
        raise ValueError("Local learning rate must be finite and positive")
    pre, dataset, pipeline, indices = load_preprocessing(config["preprocessing_manifest"])
    partition = read_json(config["partition_manifest"])
    if pre["fit_scope"] != "train_fit_only" or partition["partition_scope"] != "train_fit_only":
        raise ValueError("Only train-fit partitions/preprocessing are permitted")
    if partition["index_space"] != "zero_based_official_training_row_position":
        raise ValueError("Unsupported partition index space")
    if partition["seed"] != config["seed"]:
        raise ValueError("Run seed differs from frozen partition seed")
    links = {
        "preprocessing_manifest": artifact_ref(config["preprocessing_manifest"]),
        "dataset_manifest": pre["dataset_manifest"],
        "split_indices": pre["artifacts"]["split_indices"],
        "training_source": dataset["sources"]["train"],
    }
    for key, expected in links.items():
        if partition[key]["sha256"] != expected["sha256"]:
            raise ValueError(f"Partition source linkage mismatch: {key}")
        verify_ref(partition[key])
    for reference in partition["artifacts"].values():
        verify_ref(reference)
    clients = read_json(verify_ref(partition["artifacts"]["partition"]))
    if sorted(clients) != sorted(partition["client_ids"]) or len(clients) != fl["num_clients"]:
        raise ValueError("Client IDs/count differ from configuration")
    rows = [row for allocated in clients.values() for row in allocated]
    if any(type(row) is not int for row in rows) or sorted(rows) != sorted(
        indices["train_fit"].tolist()
    ):
        raise ValueError("Partition must cover train-fit exactly once without held-out rows")
    features, labels = features_target(load_source(dataset, "train"))
    for client, allocated in clients.items():
        if not allocated:
            raise ValueError(f"B0 requires nonempty clients: {client}")
        if class_summary(labels[allocated]) != partition["clients"][client]:
            raise ValueError(f"Partition class counts mismatch: {client}")
    values = transform(pipeline, features)
    client_data = {
        client: (values[allocated], labels[allocated]) for client, allocated in clients.items()
    }
    validation = (values[indices["validation"]], labels[indices["validation"]])
    return pre, partition, local_config, fl, policy, client_data, validation


def run_b0(config_path):
    config = read_config(config_path)
    run_dir = Path(config["run_dir"])
    if run_dir.exists() or Path(config["summary_output"]).exists():
        raise FileExistsError("B0 run/summary already exists; choose fresh paths")
    pre, partition, local_config, fl, policy, client_data, validation = load_inputs(config)
    torch.set_num_threads(config["cpu_threads"])
    torch.manual_seed(config["seed"])
    model = build_model(pre["n_features"], local_config)
    server = AsyncServer(
        model,
        sum(len(data[1]) for data in client_data.values()),
        config["server_learning_rate"],
        config["fixed_staleness_multiplier"],
    )
    settings = {**config, "max_concurrency": fl["max_concurrency"]}
    snapshot = {
        "pilot_settings": settings,
        "local_training": local_config,
        "backbone": fl,
        "policy": policy,
        "aggregation_equation": (
            "global += server_lr * (client_samples / total_train_fit) * fixed_multiplier * delta"
        ),
        "participation": "uniform random among idle clients; at most one job per client",
        "initialization_seed": config["seed"],
        "local_seed_rule": (
            "SeedSequence([run_seed, sorted_client_index, global_dispatch_index])"
            ".generate_state(1)[0]"
        ),
        "protocol_status": "Day 3 pilot; not main-experiment freeze",
        "transport": (
            "local process-pool IPC; serialized tensor payload bytes exclude IPC/framing overhead"
        ),
        "preprocessing_manifest": artifact_ref(config["preprocessing_manifest"]),
        "partition_manifest": artifact_ref(config["partition_manifest"]),
        "dataset_manifest": pre["dataset_manifest"],
        "partition_sha256": partition["artifacts"]["partition"]["sha256"],
        "configuration_sources": {
            key: artifact_ref(config[key]) for key in ("model_config", "fl_config", "policy_config")
        },
        "pilot_configuration": artifact_ref(config_path),
        "source_files": {
            name: artifact_ref(Path(__file__).with_name(name))
            for name in (
                "b0.py",
                "client.py",
                "async_server.py",
                "centralized.py",
                "preprocess.py",
                "metrics.py",
            )
        },
        "package_versions": package_versions(),
        "git": git_metadata(),
        "threshold": THRESHOLD,
        "n_features": pre["n_features"],
        "total_train_fit": server.total_samples,
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "configuration.json", snapshot)
    torch.save({"model_state": model.state_dict(), "server_version": 0}, run_dir / "initial.pt")
    curve, checkpoints = [], []
    started = time.perf_counter()

    def evaluate():
        metrics = binary_metrics(
            validation[1], predict(model, validation[0], local_config["batch_size"])
        )
        curve.append(
            {
                "server_version": server.version,
                "elapsed_seconds": time.perf_counter() - started,
                "metrics": metrics,
            }
        )

    def applied():
        if server.version % fl["evaluation_every_accepted_updates"] == 0:
            evaluate()
        if server.version % fl["checkpoint_every_accepted_updates"] == 0:
            path = run_dir / f"checkpoint_v{server.version}.pt"
            torch.save({"model_state": model.state_dict(), "server_version": server.version}, path)
            checkpoints.append(artifact_ref(path))

    try:
        evaluate()
        result = run_async(server, client_data, local_config, settings, run_dir, on_apply=applied)
        if curve[-1]["server_version"] != server.version:
            evaluate()
        torch.save(
            {"model_state": model.state_dict(), "server_version": server.version},
            run_dir / "model.pt",
        )
        write_json(run_dir / "validation.json", curve)
        history = [event for event in result["events"] if event["event"] == "apply"]
        write_json(run_dir / "version_history.json", history)
        summary = {
            "schema_version": 1,
            "status": "completed",
            "stage": "Day 3 B0 pilot",
            "seed": config["seed"],
            "policy": policy,
            "partition_sha256": snapshot["partition_sha256"],
            "aggregation_equation": snapshot["aggregation_equation"],
            "accepted_updates": result["accepted_updates"],
            "client_updates": result["client_updates"],
            "async_loop_wall_clock_seconds": result["wall_clock_seconds"],
            "pilot_wall_clock_seconds": time.perf_counter() - started,
            "serialized_download_bytes": result["serialized_download_bytes"],
            "serialized_upload_bytes": result["serialized_upload_bytes"],
            "byte_scope": snapshot["transport"],
            "validation_curve": curve,
            "checkpoints": checkpoints,
            "artifacts": {
                name: artifact_ref(run_dir / filename)
                for name, filename in {
                    "configuration": "configuration.json",
                    "events": "events.jsonl",
                    "initial_model": "initial.pt",
                    "final_model": "model.pt",
                    "validation": "validation.json",
                    "version_history": "version_history.json",
                }.items()
            },
        }
        write_json(run_dir / "manifest.json", summary)
        write_json(config["summary_output"], summary)
        return summary
    except Exception as exc:
        write_json(
            run_dir / "failure.json",
            {
                "status": "failed",
                "server_version": server.version,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        raise


def replay(run_dir):
    """Verify captured downloads/uploads and reconstruct the completion-order model.

    OS completion order is not seed-deterministic. Replay uses the recorded
    dispatch/arrival trace, without reopening raw CSVs or changing artifacts.
    """
    run_dir = Path(run_dir)
    summary = read_json(run_dir / "manifest.json")
    if summary["status"] != "completed":
        raise ValueError("Only completed B0 pilots can be replayed")
    paths = {name: verify_ref(ref) for name, ref in summary["artifacts"].items()}
    for reference in summary["checkpoints"]:
        verify_ref(reference)
    snapshot = read_json(paths["configuration"])
    settings = snapshot["pilot_settings"]
    initial = torch.load(paths["initial_model"], map_location="cpu", weights_only=True)
    model = build_model(snapshot["n_features"], snapshot["local_training"])
    model.load_state_dict(initial["model_state"], strict=True)
    server = AsyncServer(
        model,
        snapshot["total_train_fit"],
        settings["server_learning_rate"],
        settings["fixed_staleness_multiplier"],
    )
    downloads, uploads = {}, {}
    upload_bytes = download_bytes = 0
    for line in paths["events"].read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        job = event.get("job_id")
        if event["event"] in ("download", "arrival"):
            path = run_dir / event["payload_file"]
            if sha256(path) != event["payload_sha256"]:
                raise ValueError(f"SHA256 mismatch: {path}")
            payload = path.read_bytes()
            message = deserialize_message(payload)
            for key in ("job_id", "client_id", "model_start_version", "training_seed"):
                if message[key] != event[key]:
                    raise ValueError("Replay payload/event identity mismatch")
            if event["event"] == "download":
                if message["model_start_version"] != server.version:
                    raise ValueError("Replay download version mismatch")
                if any(
                    not torch.equal(t, message["model_state"][name])
                    for name, t in model.state_dict().items()
                ):
                    raise ValueError("Replay downloaded model mismatch")
                downloads[job] = event
                if event["download_bytes"] != len(payload):
                    raise ValueError("Replay download byte count mismatch")
                download_bytes += len(payload)
            else:
                if job not in downloads or message["num_samples"] != downloads[job]["num_samples"]:
                    raise ValueError("Replay arrival does not match its dispatch")
                if any(
                    message[key] != downloads[job][key]
                    for key in ("client_id", "model_start_version", "training_seed")
                ):
                    raise ValueError("Replay arrival identity mismatch")
                if event["upload_bytes"] != len(payload):
                    raise ValueError("Replay upload byte count mismatch")
                upload_bytes += len(payload)
                uploads[job] = message
        elif event["event"] == "apply":
            message = uploads.pop(job)
            receipt = server.apply_update(message, event["model_start_version"])
            if any(event[key] != value for key, value in receipt.items()):
                raise ValueError("Replay version/staleness/weight differs from recorded apply")
    final = torch.load(paths["final_model"], map_location="cpu", weights_only=True)
    if (
        uploads
        or server.version != final["server_version"]
        or server.version != summary["accepted_updates"]
    ):
        raise ValueError("Replay update count differs from completed run")
    if any(
        not torch.equal(t, final["model_state"][name]) for name, t in model.state_dict().items()
    ):
        raise ValueError("Replay final model mismatch")
    if (download_bytes, upload_bytes) != (
        summary["serialized_download_bytes"],
        summary["serialized_upload_bytes"],
    ):
        raise ValueError("Replay serialized payload totals mismatch")
    return {
        "accepted_updates": server.version,
        "final_model_matches": True,
        "serialized_download_bytes": download_bytes,
        "serialized_upload_bytes": upload_bytes,
        "events_sha256": summary["artifacts"]["events"]["sha256"],
        "final_model_sha256": summary["artifacts"]["final_model"]["sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser(
        "train", help="Run a B0 pilot without opening the official test CSV"
    )
    training.add_argument("--config", default="configs/day3_b0.yaml")
    verification = commands.add_parser(
        "replay", help="Reconstruct a recorded B0 model from its arrivals"
    )
    verification.add_argument("--run-dir", required=True)
    verification.add_argument("--output")
    args = parser.parse_args()
    if args.command == "train":
        summary = run_b0(args.config)
        print(
            json.dumps(
                {key: summary[key] for key in ("status", "accepted_updates", "client_updates")}
            )
        )
    else:
        result = replay(args.run_dir)
        if args.output:
            write_json(args.output, result)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
