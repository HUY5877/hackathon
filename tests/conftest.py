"""测试配置文件"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """模拟已登录用户的认证 Header"""
    return {"Authorization": "Bearer mock_jwt_token_for_testing"}