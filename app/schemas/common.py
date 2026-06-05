"""通用 Schema：分页、响应封装"""

from typing import Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """分页请求参数"""

    page: int = Field(
        default=1,
        ge=1,
        description="当前页码，从 1 开始",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="每页返回的数据条数，最大 100",
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应封装"""

    items: list[T] = Field(description="当前页的数据列表")
    total: int = Field(description="符合筛选条件的总数据条数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")

    @classmethod
    def from_data(cls, items: list[T], total: int, page: int, page_size: int) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return cls(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


class ApiResponse(BaseModel, Generic[T]):
    """通用 API 响应"""

    code: int = Field(
        default=0,
        description="业务状态码，0 表示成功，非 0 表示异常",
    )
    message: str = Field(
        default="ok",
        description="提示信息，成功时返回 'ok'，失败时返回错误描述",
    )
    data: T | None = Field(
        default=None,
        description="响应数据体，具体结构视接口而定",
    )