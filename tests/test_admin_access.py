"""Administrator authorization boundary tests."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, require_admin
from app.models.user import UserRole


def _client_for(user: dict) -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected(current_user: dict = Depends(require_admin)):
        return {"user_id": current_user["id"]}

    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_require_admin_rejects_developer_role():
    response = _client_for({"id": 7, "role": "developer"}).get("/protected")

    assert response.status_code == 403
    assert response.json()["detail"] == "当前账号没有管理权限"


def test_require_admin_accepts_admin_string_role():
    response = _client_for({"id": 1, "role": "admin"}).get("/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": 1}


def test_require_admin_accepts_admin_enum_role():
    response = _client_for({"id": 2, "role": UserRole.ADMIN}).get("/protected")

    assert response.status_code == 200
    assert response.json() == {"user_id": 2}
