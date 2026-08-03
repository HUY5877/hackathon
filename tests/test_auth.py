"""认证链端到端测试：注册 / 登录 / JWT 校验（走真实本地 Postgres 测试库）。"""
from app.core import security

REG = {"email": "alice@example.com", "username": "alice", "password": "pw123456"}


def _register(client, **overrides):
    payload = {**REG, **overrides}
    return client.post("/api/v1/auth/register", json=payload)


def test_register_success_returns_token_and_user(client):
    r = _register(client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == REG["email"]
    assert data["user"]["username"] == REG["username"]
    assert "hashed_password" not in data["user"]   # 不泄露密码


def test_register_duplicate_email_returns_409(client):
    _register(client)
    r = _register(client, username="alice2")        # 同 email 不同用户名
    assert r.status_code == 409


def test_login_success_returns_token(client):
    _register(client)
    r = client.post("/api/v1/auth/login",
                    json={"email": REG["email"], "password": REG["password"]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["access_token"]


def test_login_wrong_password_returns_401(client):
    _register(client)
    r = client.post("/api/v1/auth/login",
                    json={"email": REG["email"], "password": "wrong-pw"})
    assert r.status_code == 401


def test_login_nonexistent_email_returns_401(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401


def test_issued_token_decodes_to_registered_user_id(client):
    data = _register(client).json()["data"]
    token, user_id = data["access_token"], data["user"]["id"]
    assert security.decode_access_token(token) == user_id


def test_invalid_token_decodes_to_none(client):
    assert security.decode_access_token("garbage.token.value") is None
