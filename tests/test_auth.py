from unittest.mock import patch

import redis as redis_lib

import fastapi_k8s.main as app_mod


def _login(client, username="admin", password="admin"):
    return client.post("/login", json={"username": username, "password": password})


def test_login_valid(client, mock_redis):
    r = _login(client)
    assert r.status_code == 200
    data = r.json()
    assert data["message"] == "logged in"
    assert data["username"] == "admin"
    assert "session_id" in r.cookies


def test_login_bad_password(client, mock_redis):
    r = _login(client, password="wrong")
    assert r.status_code == 401


def test_login_unknown_user(client, mock_redis):
    r = _login(client, username="nobody", password="x")
    assert r.status_code == 401


def test_me_without_cookie(client, mock_redis):
    r = client.get("/me")
    assert r.status_code == 401


def test_me_with_valid_session(client, mock_redis):
    login_resp = _login(client)
    session_id = login_resp.cookies["session_id"]
    r = client.get("/me", cookies={"session_id": session_id})
    assert r.status_code == 200
    data = r.json()
    assert data["username"] == "admin"
    assert "server" in data


def test_me_with_invalid_session(client, mock_redis):
    r = client.get("/me", cookies={"session_id": "bogus"})
    assert r.status_code == 401


def test_logout_clears_session(client, mock_redis):
    login_resp = _login(client)
    session_id = login_resp.cookies["session_id"]
    logout_resp = client.post("/logout", cookies={"session_id": session_id})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "logged out"
    r = client.get("/me", cookies={"session_id": session_id})
    assert r.status_code == 401


def test_session_persists_across_requests(client, mock_redis):
    login_resp = _login(client)
    session_id = login_resp.cookies["session_id"]
    for _ in range(3):
        r = client.get("/me", cookies={"session_id": session_id})
        assert r.status_code == 200
        assert r.json()["username"] == "admin"


def test_login_redis_unavailable(client):
    fake = patch.object(
        app_mod, "_get_redis", side_effect=redis_lib.ConnectionError
    )
    with fake:
        r = _login(client)
    assert r.status_code == 503


def test_logout_without_cookie(client, mock_redis):
    r = client.post("/logout")
    assert r.status_code == 200
    assert r.json()["message"] == "logged out"


def test_login_user_account(client, mock_redis):
    r = _login(client, username="user", password="user")
    assert r.status_code == 200
    session_id = r.cookies["session_id"]
    me_resp = client.get("/me", cookies={"session_id": session_id})
    assert me_resp.json()["username"] == "user"
