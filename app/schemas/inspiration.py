"""灵感池 Schema — PGC 案例拆解内容的请求/响应"""

from datetime import datetime
from pydantic import BaseModel, Field


# ── 请求 ────────────────────────────────────

class InspirationFilterParams(BaseModel):
    """灵感池内容筛选器"""

    category_tags: list[str] | None = Field(
        default=None,
        description="内容分类标签，多选，如 ['AI应用', 'Web3', '教育科技', '游戏开发']",
    )
    tech_tags: list[str] | None = Field(
        default=None,
        description="技术栈标签，多选，如 ['Python', 'GPT-4', 'LangChain', 'Solidity']",
    )
    difficulty_level: str | None = Field(
        default=None,
        description="项目难度: 'beginner'(新手可复现) / 'intermediate'(进阶) / 'advanced'(高级)",
    )
    keyword: str | None = Field(
        default=None,
        description="关键词模糊搜索，同时匹配标题和摘要",
    )
    sort_by: str = Field(
        default="created_at",
        description="排序字段: 'created_at'(按发布时间) / 'like_count'(按点赞数) / 'view_count'(按浏览量)",
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


class InteractionRequest(BaseModel):
    """用户与灵感内容的交互请求（点赞 / 收藏）"""

    item_id: int = Field(
        description="目标灵感内容的唯一 ID",
    )
    interaction_type: str = Field(
        description="交互类型: 'like'(点赞) / 'bookmark'(收藏)",
    )


# ── 响应 ────────────────────────────────────

class InspirationSummaryResponse(BaseModel):
    """
    灵感池内容公开摘要

    游客（未登录）可见的字段集合。
    包含案例基本信息、标签、互动数据，但不含核心拆解内容。
    """

    id: int = Field(description="内容唯一 ID")
    title: str = Field(description="案例标题，如 '【AI教育】ETHGlobal 2025 冠军项目拆解'")
    slug: str = Field(description="URL 友好的唯一标识符，用于详情页路由")
    summary: str | None = Field(default=None, description="案例简短摘要，200 字以内，概述项目亮点")
    teaser: str | None = Field(default=None, description="诱饵文案，用于注册墙拦截页，展示核心干货的只言片语吸引用户注册")
    source_hackathon_name: str | None = Field(default=None, description="案例来源的黑客松赛事名称")
    team_name: str | None = Field(default=None, description="参赛团队名称")
    prize_won: str | None = Field(default=None, description="获奖情况，如 '总冠军 + $50,000' / 'AI赛道一等奖'")
    category_tags: list[str] | None = Field(default=None, description="内容分类标签，如 ['AI应用', '教育科技']")
    tech_tags: list[str] | None = Field(default=None, description="项目使用的技术栈标签，如 ['GPT-4', 'LangChain', 'Next.js']")
    difficulty_level: str | None = Field(default=None, description="项目难度: 'beginner' / 'intermediate' / 'advanced'")
    cover_image_url: str | None = Field(default=None, description="封面图片 URL")
    like_count: int = Field(description="点赞数")
    bookmark_count: int = Field(description="收藏数")
    view_count: int = Field(description="浏览量")
    is_featured: bool = Field(description="是否为精选推荐，true 表示在首页突出展示")
    created_at: datetime = Field(description="内容发布时间")

    class Config:
        from_attributes = True


class InspirationDetailResponse(InspirationSummaryResponse):
    """
    灵感池内容完整详情

    继承公开摘要的全部字段，额外包含核心拆解内容。
    需要登录后才能获取，未登录请求时这些字段为 null。

    对应 PRD 模块一：强制注册墙（Reg-Wall）机制
    """

    full_content: str | None = Field(
        default=None,
        description="完整案例拆解内容（Markdown 格式），包含项目背景、技术架构、创新点、心得等。需登录查看",
    )
    team_profile: dict | None = Field(
        default=None,
        description="团队画像，如 {'size': 3, 'roles': ['全栈', 'AI工程师', '设计师'], 'background': 'MIT研究生'}",
    )
    video_url: str | None = Field(
        default=None,
        description="项目演示视频链接（YouTube / Bilibili 等），需登录查看",
    )
    source_code_url: str | None = Field(
        default=None,
        description="项目源码仓库链接（GitHub 等），需登录查看",
    )
    demo_url: str | None = Field(
        default=None,
        description="在线 Demo 地址，需登录查看",
    )
    source_hackathon_url: str | None = Field(
        default=None,
        description="源黑客松赛事页面链接，需登录查看",
    )

    class Config:
        from_attributes = True