"""app/core/security.py 单元测试（纯函数，不依赖数据库）"""
from app.core import security


def test_hash_and_verify_password_roundtrip():
    hashed = security.hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"          # 已哈希，不是明文
    assert security.verify_password("s3cret-pw", hashed) is True
    assert security.verify_password("wrong-pw", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = security.create_access_token(42)
    assert isinstance(token, str) and token.count(".") == 2   # JWT 三段式
    assert security.decode_access_token(token) == 42


def test_decode_invalid_token_returns_none():
    assert security.decode_access_token("not-a-real-token") is None
    assert security.decode_access_token("mock_jwt_abc") is None
