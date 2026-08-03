"""ORM 模型聚合

将所有模型导入到此模块，便于：
- Alembic autogenerate 发现所有表
- 外部代码统一 `from app.models import Hackathon, User, ...`
"""

from app.models.user import User, UserRole
from app.models.hackathon import Hackathon, HackathonMode, HackathonStatus
from app.models.inspiration import InspirationItem, UserInteraction
from app.models.empowerment import EmpowermentArticle, ContentType

__all__ = [
    "User",
    "UserRole",
    "Hackathon",
    "HackathonMode",
    "HackathonStatus",
    "InspirationItem",
    "UserInteraction",
    "EmpowermentArticle",
    "ContentType",
]
