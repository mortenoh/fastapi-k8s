import fastapi_k8s.main as app_mod


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "message" in data
    assert "server" in data


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_ready_when_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_ready_after_disable(client):
    client.post("/ready/disable")
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not ready"}


def test_ready_enable(client):
    app_mod._ready = False
    r = client.post("/ready/enable")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_ready_disable(client):
    r = client.post("/ready/disable")
    assert r.status_code == 200
    assert r.json() == {"status": "not ready"}


def test_ready_toggle_roundtrip(client):
    client.post("/ready/disable")
    assert client.get("/ready").status_code == 503
    client.post("/ready/enable")
    assert client.get("/ready").status_code == 200


def test_stress(client):
    r = client.get("/stress?seconds=1")
    assert r.status_code == 200
    data = r.json()
    assert data["stressed_seconds"] == 1
    assert "server" in data


def test_config(client):
    r = client.get("/config")
    assert r.status_code == 200
    data = r.json()
    assert "app_name" in data
    assert "log_level" in data
    assert "max_stress_seconds" in data


def test_version(client):
    r = client.get("/version")
    assert r.status_code == 200
    data = r.json()
    assert "version" in data
    assert "server" in data


def test_info(client):
    r = client.get("/info")
    assert r.status_code == 200
    data = r.json()
    assert "pod_name" in data
    assert "pod_ip" in data
    assert "node_name" in data
    assert "namespace" in data
    assert "cpu_request" in data
    assert "cpu_limit" in data
    assert "memory_request" in data
    assert "memory_limit" in data
