"""Administrator control-plane request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminUserResponse(BaseModel):
    """Safe user fields exposed to administrators."""

    id: int
    email: str
    username: str
    role: str
    email_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeletedResourceResponse(BaseModel):
    """Identity of a resource removed by an administrator."""

    id: int = Field(description="Deleted resource ID")
    name: str = Field(description="Deleted resource display name")
