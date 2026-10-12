import copy
import json

import pytest

from src.monitor import StateMonitor


def trace():
    fast = dict(client_id="fast", job_id="j0", model_start_version=0, training_seed=7)
    slow = dict(client_id="slow", job_id="j1", model_start_version=0, training_seed=8)
    return [
        dict(fast, event="download", elapsed_seconds=1.0, num_samples=2),
        dict(slow, event="download", elapsed_seconds=1.0, num_samples=5),
        dict(
            fast,
            event="arrival",
            elapsed_seconds=3.0,
            arrival_elapsed_seconds=0.5,
            server_version=0,
            staleness=0,
            local_train_seconds=1.5,
        ),
        dict(
            fast,
            event="apply",
            elapsed_seconds=3.0,
            version_before=0,
            version_after=1,
            staleness=0,
            num_samples=2,
        ),
        dict(
            slow,
            event="arrival",
            elapsed_seconds=8.0,
            server_version=1,
            staleness=1,
            local_train_seconds=6.0,
        ),
        dict(
            slow,
            event="apply",
            elapsed_seconds=9.0,
            version_before=1,
            version_after=2,
            staleness=1,
            num_samples=5,
        ),
    ]


def monitor():
    return StateMonitor({"fast": 2, "slow": 5, "idle": 9}, run_id="fixture")


def history(events):
    state = monitor()
    rows = [state.snapshot()]
    for event in events:
        state.consume(event)
        rows.append(state.snapshot())
    return rows


def fields(rows, client):
    return next(row["fields"] for row in rows if row["client_id"] == client)


def test_hand_calculated_startup_arrival_apply_and_idle_state():
    states = history(trace())
    start = fields(states[0], "fast")
    assert start["num_samples"]["value"] == 2
    assert start["num_samples"]["available_at"] == {"event_index": 0, "elapsed_seconds": 0.0}
    assert start["previous_local_train_seconds"]["status"] == "not_yet_observed"
    assert start["contribution_age_seconds"]["status"] == "never_contributed"
    for field in ("rtt_seconds", "throughput_bytes_per_second"):
        assert start[field]["value"] is None
        assert start[field]["status"] == "unmeasured_process_pool_ipc"
        assert start[field]["available_at"] is None
    arrived = fields(states[3], "fast")
    assert arrived["previous_local_train_seconds"]["value"] == 1.5
    assert arrived["previous_local_train_seconds"]["available_at"] == {
        "event_index": 3,
        "elapsed_seconds": 3.0,
    }
    assert arrived["last_arrival_staleness"]["value"] == 0
    assert arrived["contribution_age_seconds"]["value"] is None
    assert fields(states[4], "fast")["contribution_age_seconds"]["value"] == 0.0
    assert fields(states[6], "fast")["contribution_age_seconds"]["value"] == 6.0
    assert fields(states[6], "slow")["last_arrival_staleness"]["value"] == 1
    assert fields(states[6], "slow")["contribution_age_seconds"]["value"] == 0.0
    assert fields(states[6], "idle")["num_samples"]["value"] == 9
    assert fields(states[6], "idle")["contribution_age_seconds"]["value"] is None
    assert {r["server_version"] for r in states[6]} == {2}
    json.dumps(states, allow_nan=False)


def test_every_prefix_is_independent_of_future_values_and_suffix_length():
    events = trace()
    original = history(events)
    for boundary in range(len(events) + 1):
        assert history(events[:boundary]) == original[: boundary + 1]
    changed = copy.deepcopy(events)
    changed[4]["local_train_seconds"] = 900.0
    changed[5]["elapsed_seconds"] = 1000.0
    assert history(changed)[:5] == original[:5]
    assert fields(original[2], "fast")["previous_local_train_seconds"]["value"] is None
    for prefix in original:
        for row in prefix:
            for field in row["fields"].values():
                for time in (field["observed_at"], field["available_at"]):
                    if time is not None:
                        assert time["event_index"] <= row["through_event_index"]
                        assert time["elapsed_seconds"] <= row["observation_elapsed_seconds"]
                for source in field["source"]:
                    assert source["event_index"] <= row["through_event_index"]


def test_input_and_output_mutation_cannot_rewrite_history():
    state = monitor()
    events = trace()
    before = copy.deepcopy(events)
    for event in events[:3]:
        state.consume(event)
    snapshot = state.snapshot()
    saved = copy.deepcopy(snapshot)
    assert events == before
    events[2]["local_train_seconds"] = 100
    snapshot[0]["fields"]["num_samples"]["value"] = -1
    assert state.snapshot() == saved
    state.consume(events[3])
    assert saved[0]["server_version"] == 0


@pytest.mark.parametrize(
    "value,status",
    [
        (0.0, "observed"),
        (None, "missing_observation"),
        (-1, "invalid_observation"),
        (True, "invalid_observation"),
        ("1", "invalid_observation"),
        (float("nan"), "invalid_observation"),
        (float("inf"), "invalid_observation"),
    ],
)
def test_duration_missing_invalid_and_valid_zero(value, status):
    events = trace()[:3]
    events[2]["local_train_seconds"] = value
    field = fields(history(events)[-1], "fast")["previous_local_train_seconds"]
    assert field["status"] == status
    assert field["value"] == (0.0 if status == "observed" else None)


@pytest.mark.parametrize("counts", [{}, {"a": 0}, {"a": True}, {"a": 1.5}, {1: 2}])
def test_bad_client_metadata_fails(counts):
    with pytest.raises(ValueError):
        StateMonitor(counts, run_id="fixture")


@pytest.mark.parametrize(
    "position,changes",
    [
        (0, {"elapsed_seconds": -1}),
        (1, {"elapsed_seconds": 0.9}),
        (0, {"elapsed_seconds": float("nan")}),
        (0, {"elapsed_seconds": True}),
        (0, {"elapsed_seconds": "1"}),
        (0, {"event": "unknown"}),
        (0, {"client_id": "unknown"}),
        (0, {"job_id": None}),
        (0, {"num_samples": 3}),
        (0, {"num_samples": True}),
        (0, {"model_start_version": 1}),
        (0, {"training_seed": True}),
        (1, {"job_id": "j0"}),
        (1, {"client_id": "fast", "num_samples": 2}),
        (2, {"job_id": "unknown"}),
        (2, {"training_seed": 8}),
        (2, {"staleness": 1}),
        (2, {"server_version": True}),
        (3, {"num_samples": 5}),
        (3, {"version_before": 1}),
        (3, {"version_after": 2}),
        (3, {"staleness": True}),
    ],
)
def test_malformed_event_is_rejected_without_changing_state(position, changes):
    state = monitor()
    events = trace()
    for event in events[:position]:
        state.consume(event)
    before = state.snapshot()
    with pytest.raises(ValueError):
        state.consume({**events[position], **changes})
    assert state.snapshot() == before


def test_duplicate_or_out_of_order_lifecycle_is_rejected():
    events = trace()
    for sequence in (
        [events[2]],
        [events[0], events[3]],
        events[:3] + [events[4]],
        events[:4] + [events[0] | {"elapsed_seconds": 4}],
    ):
        with pytest.raises(ValueError):
            history(sequence)


@pytest.mark.parametrize("with_arrival", [False, True])
def test_reject_and_failure_never_count_as_a_contribution(with_arrival):
    events = trace()
    prefix = events[:3] if with_arrival else events[:2]
    reject = {**events[2], "event": "reject", "elapsed_seconds": 4.0}
    failure = {"event": "failure", "elapsed_seconds": 5.0, "server_version": 0}
    state = monitor()
    for event in prefix + [reject, failure]:
        state.consume(event)
    rows = state.snapshot()
    assert {row["server_version"] for row in rows} == {0}
    assert fields(rows, "fast")["contribution_age_seconds"]["value"] is None
    expected_duration = 1.5 if with_arrival else None
    assert fields(rows, "fast")["previous_local_train_seconds"]["value"] == expected_duration
    with pytest.raises(ValueError, match="failure"):
        state.consume(failure)


def test_missing_new_duration_does_not_disguise_old_measurement():
    events = trace()[:4]
    next_job = dict(client_id="fast", job_id="j2", model_start_version=1, training_seed=9)
    events += [
        dict(next_job, event="download", elapsed_seconds=4, num_samples=2),
        dict(next_job, event="arrival", elapsed_seconds=5, server_version=1, staleness=0),
    ]
    field = fields(history(events)[-1], "fast")["previous_local_train_seconds"]
    assert field["value"] is None
    assert field["status"] == "missing_observation"
    assert field["available_at"]["event_index"] == 6


def test_future_rejection_cannot_change_prior_prefix():
    events = trace()
    changed = copy.deepcopy(events)
    changed[5] = {**events[4], "event": "reject", "elapsed_seconds": 9}
    changed.append(dict(event="failure", elapsed_seconds=10, server_version=1))
    assert history(changed)[:6] == history(events)[:6]
