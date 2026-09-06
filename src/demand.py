"""Demand-estimation module: state -> (d_part, d_budget)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientState:
    num_samples: int
    prev_local_train_sec: float
    rtt_ms: float
    throughput_mbps: float
    staleness: int
    age_since_last_update: float


def estimate_demand(state: ClientState) -> tuple[float, float]:
    raise NotImplementedError("Gunakan rule transparan yang dikalibrasi lalu dibekukan.")
