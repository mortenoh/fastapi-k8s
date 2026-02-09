from unittest.mock import patch

import redis as redis_lib

import fastapi_k8s.main as app_mod


def test_visits(client, mock_redis):
    r = client.get("/visits")
    assert r.status_code == 200
    data = r.json()
    assert data["visits"] == 1


def test_visits_increments(client, mock_redis):
    client.get("/visits")
    r = client.get("/visits")
    assert r.json()["visits"] == 2


def test_kv_missing(client, mock_redis):
    r = client.get("/kv/nonexistent")
    assert r.status_code == 404


def test_kv_roundtrip(client, mock_redis):
    client.post("/kv/greeting", json={"value": "hello"})
    r = client.get("/kv/greeting")
    assert r.status_code == 200
    assert r.json() == {"key": "greeting", "value": "hello"}


def test_kv_overwrite(client, mock_redis):
    client.post("/kv/key1", json={"value": "first"})
    client.post("/kv/key1", json={"value": "second"})
    r = client.get("/kv/key1")
    assert r.json()["value"] == "second"


def test_visits_redis_connection_error(client):
    with patch.object(app_mod, "_get_redis", side_effect=redis_lib.ConnectionError):
        r = client.get("/visits")
    assert r.status_code == 503


def test_visits_redis_generic_error(client):
    with patch.object(app_mod, "_get_redis", side_effect=Exception("boom")):
        r = client.get("/visits")
    assert r.status_code == 500


def test_kv_get_redis_connection_error(client):
    with patch.object(app_mod, "_get_redis", side_effect=redis_lib.ConnectionError):
        r = client.get("/kv/test")
    assert r.status_code == 503


def test_kv_set_redis_connection_error(client):
    with patch.object(app_mod, "_get_redis", side_effect=redis_lib.ConnectionError):
        r = client.post("/kv/test", json={"value": "hello"})
    assert r.status_code == 503
