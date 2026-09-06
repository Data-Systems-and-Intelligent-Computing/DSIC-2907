"""Asynchronous FL server: immediate apply, versioning, staleness logging."""


class AsyncServer:
    def __init__(self):
        self.version = 0

    def apply_update(self, client_update, model_start_version: int):
        staleness = self.version - model_start_version
        raise NotImplementedError("Apply update dengan aggregation/staleness rule yang dibekukan.")
