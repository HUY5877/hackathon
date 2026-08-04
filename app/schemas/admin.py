"""Administrator control-plane request and response schemas."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class AdminHackathonUpdate(BaseModel):
    """Strict whitelist of hackathon fields administrators may edit."""

    name: str | None = Field(default=None, max_length=500)
    summary: str | None = Field(default=None, max_length=500)
    description: str | None = None
    status: Literal["upcoming", "registering", "ongoing", "ended"] | None = None
    mode: Literal["online", "offline", "hybrid"] | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    track_tags: list[str] | None = None
    tech_tags: list[str] | None = None
    prize_pool: str | None = Field(default=None, max_length=200)
    prize_pool_usd: float | None = Field(default=None, ge=0)
    expected_participants: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    registration_url: str | None = Field(default=None, max_length=1000)
    organizer: str | None = Field(default=None, max_length=300)
    sponsors: list[str] | None = None
    cover_image: str | None = Field(default=None, max_length=1000)
    is_verified: bool | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("registration_url", "cover_image")
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL 必须使用 http 或 https")
        return value

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个可编辑字段")
        if "name" in self.model_fields_set:
            if self.name is None or not self.name.strip():
                raise ValueError("赛事名称不能为空")
            self.name = self.name.strip()
        for required_field in ("status", "mode", "is_verified"):
            if required_field in self.model_fields_set and getattr(self, required_field) is None:
                raise ValueError(f"{required_field} 不能为空")
        if (
            "registration_start" in self.model_fields_set
            and "registration_end" in self.model_fields_set
            and self.registration_start is not None
            and self.registration_end is not None
            and self.registration_start > self.registration_end
        ):
            raise ValueError("报名开始时间不能晚于结束时间")
        if (
            "event_start" in self.model_fields_set
            and "event_end" in self.model_fields_set
            and self.event_start is not None
            and self.event_end is not None
            and self.event_start > self.event_end
        ):
            raise ValueError("赛事开始时间不能晚于结束时间")
        return self


class AdminHackathonDeleteRequest(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")


class AdminHackathonResponse(BaseModel):
    """Full editable and read-only hackathon fields for the admin drawer."""

    id: int
    name: str
    slug: str
    description: str | None = None
    summary: str | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    status: str
    mode: str
    track_tags: list[str] | None = None
    tech_tags: list[str] | None = None
    prize_pool: str | None = None
    prize_pool_usd: float | None = None
    expected_participants: int | None = None
    location: str | None = None
    country: str | None = None
    city: str | None = None
    source_url: str
    source_platform: str
    registration_url: str | None = None
    organizer: str | None = None
    sponsors: list[str] | None = None
    cover_image: str | None = None
    is_verified: bool
    llm_confidence: float | None = None
    view_count: int
    external_click_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
