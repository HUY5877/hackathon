"""黑客松赛事 Schema — 信息大厅的请求/响应"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


# ── 请求 ────────────────────────────────────

class HackathonFilterParams(BaseModel):
    """
    信息大厅多维筛选器

    对应 PRD 模块四：前端列表展示与筛选
    支持按赛事状态、形式、赛道、技术栈、地区等多维度组合筛选
    """

    status: str | None = Field(
        default=None,
        description="赛事状态: 'upcoming'(即将开始) / 'registering'(报名中) / 'ongoing'(进行中) / 'ended'(已结束)",
    )
    mode: str | None = Field(
        default=None,
        description="赛事形式: 'online'(线上) / 'offline'(线下) / 'hybrid'(线上+线下)",
    )
    track_tags: list[str] | None = Field(
        default=None,
        description="赛道标签，支持多选，如 ['AI应用', 'Web3', '教育科技']",
    )
    tech_tags: list[str] | None = Field(
        default=None,
        description="技术栈标签，支持多选，如 ['Python', 'Solidity', 'React']",
    )
    country: str | None = Field(
        default=None,
        description="国家/地区筛选，如 'China' / 'Global' / 'Australia'",
    )
    keyword: str | None = Field(
        default=None,
        description="关键词模糊搜索，同时匹配赛事名称和摘要",
    )
    sort_by: str = Field(
        default="event_start",
        description="排序字段: 'event_start'(按赛事开始时间) / 'prize_pool_usd'(按奖金池) / 'view_count'(按浏览量) / 'created_at'(按录入时间)",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="当前页码",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="每页条数",
    )


class HackathonSearchRequest(BaseModel):
    """关键词搜索请求"""

    keyword: str = Field(
        min_length=1,
        description="搜索关键词，最少 1 个字符",
    )


# ── 响应 ────────────────────────────────────

class HackathonSummaryResponse(BaseModel):
    """赛事列表摘要（不含完整长文本描述，减少数据传输量）"""

    id: int = Field(description="赛事唯一 ID")
    name: str = Field(description="赛事名称")
    slug: str = Field(description="URL 友好的唯一标识符，用于详情页路由")
    summary: str | None = Field(default=None, description="AI 生成的一句话摘要，50 字以内")
    registration_start: datetime | None = Field(default=None, description="报名开始时间")
    registration_end: datetime | None = Field(default=None, description="报名截止时间")
    event_start: datetime | None = Field(default=None, description="赛事开始时间")
    event_end: datetime | None = Field(default=None, description="赛事结束时间")
    status: str = Field(description="赛事状态: 'upcoming' / 'registering' / 'ongoing' / 'ended'")
    mode: str = Field(description="赛事形式: 'online'(线上) / 'offline'(线下) / 'hybrid'(混合)")
    track_tags: list[str] | None = Field(default=None, description="赛道标签，如 ['AI应用', 'Web3', '教育科技']")
    tech_tags: list[str] | None = Field(default=None, description="涉及的技术栈标签，如 ['Python', 'React', 'Solidity']")
    prize_pool: str | None = Field(default=None, description="奖金池原始描述，如 '$150,000 USD' / '¥600,000 CNY'")
    prize_pool_usd: float | None = Field(default=None, description="奖金池标准化 USD 金额，用于排序和比较")
    location: str | None = Field(default=None, description="赛事地点，如 'Sydney, Australia' / '北京' / '线上'")
    country: str | None = Field(default=None, description="赛事所在国家/地区，如 'China' / 'Global' / 'Australia'")
    source_platform: str = Field(description="数据来源平台，如 'devpost' / 'mlh' / 'dorahacks' / 'eventbrite'")
    source_url: str = Field(description="数据来源的原始页面 URL")
    registration_url: str | None = Field(default=None, description="官方报名页面链接，点击「去官网报名」时跳转")
    organizer: str | None = Field(default=None, description="主办方名称")
    view_count: int = Field(description="平台内浏览量")
    external_click_count: int = Field(description="「去官网报名」外链点击次数，用于转化追踪")
    cover_image: str | None = Field(default=None, description="赛事封面图/海报 URL，列表页展示用")
    created_at: datetime = Field(description="数据录入时间")

    model_config = ConfigDict(from_attributes=True)


class HackathonDetailResponse(HackathonSummaryResponse):
    """赛事详情（继承列表摘要，额外包含完整描述和扩展字段）"""

    description: str | None = Field(default=None, description="赛事完整描述，长文本")
    expected_participants: int | None = Field(default=None, description="预计参与人数")
    sponsors: list[str] | None = Field(default=None, description="赞助商列表，如 ['Ethereum Foundation', 'Polygon']")
    city: str | None = Field(default=None, description="赛事所在城市，如 'Sydney' / 'Beijing' / 'Hong Kong'")
    is_verified: bool = Field(description="是否经过人工审核确认，true 表示数据可信")

    model_config = ConfigDict(from_attributes=True)


class ExternalClickResponse(BaseModel):
    """
    外链点击记录响应

    对应 PRD 模块四：官方外链跳转直达
    用户点击「去官网报名」时记录转化数据
    """

    click_id: int = Field(description="点击记录 ID")
    message: str = Field(
        default="点击已记录，正在跳转...",
        description="前端提示文案",
    )