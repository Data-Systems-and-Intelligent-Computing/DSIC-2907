import pytest
import torch

from src.client import deserialize_message, measure_message, serialize_message


def test_dense_messages_count_exact_serialized_bytes_and_overhead():
    tensors = {"weight": torch.ones(3, 2, dtype=torch.float32)}
    download = serialize_message({"job_id": "job_0000", "model_state": tensors})
    upload = serialize_message({"job_id": "job_0000", "delta": tensors, "num_samples": 10})

    for payload in (download, upload):
        measured = measure_message(payload, tensors)
        assert measured["payload_bytes"] == len(payload)
        assert measured["frame_bytes"] == 0
        assert measured["tensor_value_bytes"] == 3 * 2 * 4
        assert measured["serialization_overhead_bytes"] > 0
        assert measured["tensor_value_bytes"] + measured["serialization_overhead_bytes"] == len(
            payload
        )
    assert deserialize_message(download)["model_state"]["weight"].shape == (3, 2)
    assert deserialize_message(upload)["delta"]["weight"].shape == (3, 2)


@pytest.mark.parametrize("payload", [None, "bytes", b"", b"not a torch message"])
def test_empty_or_unreadable_payload_is_rejected(payload):
    with pytest.raises(ValueError, match="payload"):
        deserialize_message(payload)


def test_message_measurement_rejects_missing_or_invalid_tensors():
    payload = serialize_message({"delta": {"weight": torch.ones(2)}})
    with pytest.raises(ValueError, match="dense tensors"):
        measure_message(payload, {})
    with pytest.raises(ValueError, match="dense tensors"):
        measure_message(payload, {"weight": "not a tensor"})
