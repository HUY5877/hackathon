"""开发者赋能 Schema — Vibecoding 教程 & 参赛指南的请求/响应"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


# ── 请求 ────────────────────────────────────

class EmpowermentFilterParams(BaseModel):
    """开发者赋能内容筛选器"""

    content_type: str | None = Field(
        default=None,
        description="内容大类: 'vibecoding'(AI辅助编程教程) / 'guide'(黑客松参赛指南)",
    )
    sub_category: str | None = Field(
        default=None,
        description=(
            "内容子分类。vibecoding 下: 'cursor' / 'copilot' / 'chatgpt' / 'windsurf' / 'general'；"
            "guide 下: 'process'(全流程) / 'pitch_deck'(路演PPT) / 'teaming'(组队)"
        ),
    )
    difficulty_level: str | None = Field(
        default=None,
        description="教程难度: 'beginner'(零基础入门) / 'intermediate'(有一定基础) / 'advanced'(高级技巧)",
    )
    tags: list[str] | None = Field(
        default=None,
        description="通用标签，多选，如 ['Cursor', 'React', 'Pitch Deck']",
    )
    keyword: str | None = Field(
        default=None,
        description="关键词模糊搜索，同时匹配标题和摘要",
    )
    sort_by: str = Field(
        default="created_at",
        description="排序字段: 'created_at'(按发布时间) / 'view_count'(按浏览量) / 'like_count'(按点赞数)",
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


# ── 响应 ────────────────────────────────────

class EmpowermentArticleResponse(BaseModel):
    """
    赋能文章响应

    对应 PRD 模块三：开发者赋能与 Vibecoding 专区
    包含 AI 辅助编程教程（Vibecoding）和黑客松软技能指南两类内容
    """

    id: int = Field(description="文章唯一 ID")
    title: str = Field(description="文章标题，如 '【Cursor 入门】从零到一：用自然语言构建你的第一个 Web 应用'")
    slug: str = Field(description="URL 友好的唯一标识符，用于详情页路由")
    content_type: str = Field(
        description="内容大类: 'vibecoding'(AI辅助编程教程) / 'guide'(黑客松参赛指南)",
    )
    sub_category: str | None = Field(
        default=None,
        description=(
            "内容子分类。vibecoding: 'cursor' / 'copilot' / 'chatgpt' / 'windsurf' / 'general'；"
            "guide: 'process'(全流程科普) / 'pitch_deck'(路演PPT指南) / 'teaming'(组队策略)"
        ),
    )
    summary: str | None = Field(default=None, description="文章摘要，200 字以内")
    full_content: str | None = Field(default=None, description="文章完整内容（Markdown 格式），包含详细步骤和示例")
    difficulty_level: str | None = Field(default=None, description="教程难度: 'beginner' / 'intermediate' / 'advanced'")
    estimated_read_time: int | None = Field(default=None, description="预计阅读时长，单位分钟")
    tags: list[str] | None = Field(default=None, description="通用标签，如 ['Cursor', 'React', 'TypeScript', 'Web开发']")
    cover_image_url: str | None = Field(default=None, description="封面图片 URL")
    video_url: str | None = Field(default=None, description="关联视频教程链接（YouTube / Bilibili 等）")
    external_url: str | None = Field(default=None, description="外部参考链接（如官方文档、相关工具官网）")
    view_count: int = Field(description="浏览量")
    like_count: int = Field(description="点赞数")
    is_featured: bool = Field(description="是否为精选内容，true 表示在赋能区首页突出展示")
    created_at: datetime = Field(description="文章发布时间")
    updated_at: datetime = Field(description="文章最后更新时间")

    model_config = ConfigDict(from_attributes=True)