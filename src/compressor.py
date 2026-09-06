"""Magnitude top-k compressor dan byte-accurate serialization accounting."""


def topk_compress(delta, budget: float):
    raise NotImplementedError


def serialized_size_bytes(payload) -> int:
    raise NotImplementedError
