from app.services.auth_service import auth_service
from app.services.hackathon_service import hackathon_service
from app.services.inspiration_service import inspiration_service
from app.services.recommendation_service import recommendation_service
from app.services.empowerment_service import empowerment_service
from app.services.edm_service import edm_service
from app.services.user_service import user_service

__all__ = [
    "auth_service",
    "hackathon_service",
    "inspiration_service",
    "recommendation_service",
    "empowerment_service",
    "edm_service",
    "user_service",
]