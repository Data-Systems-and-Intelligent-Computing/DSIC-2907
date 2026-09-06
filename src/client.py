"""Logical FL client dengan local training yang tetap antar-policy."""


class FLClient:
    def train(self, global_model, local_data):
        raise NotImplementedError
