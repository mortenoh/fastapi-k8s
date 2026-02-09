from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import fastapi_k8s.main as app_mod


@pytest.fixture()
def client():
    return TestClient(app_mod.app)


@pytest.fixture(autouse=True)
def reset_ready():
    app_mod._ready = True
    yield
    app_mod._ready = True


@pytest.fixture()
def mock_redis():
    store = {}
    fake = MagicMock()

    def fake_get(key):
        return store.get(key)

    def fake_set(key, value):
        store[key] = value

    def fake_incr(key):
        store[key] = store.get(key, 0) + 1
        return store[key]

    fake.get = MagicMock(side_effect=fake_get)
    fake.set = MagicMock(side_effect=fake_set)
    fake.incr = MagicMock(side_effect=fake_incr)

    with patch.object(app_mod, "_get_redis", return_value=fake):
        yield fake
