def test_staleness_definition():
    server_version = 7
    model_start_version = 4
    assert server_version - model_start_version == 3
