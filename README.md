# 黑客松信息聚合与开发者赋能平台 — 后端

## 技术栈

| 层级 | 技术 |
|------|------|
| **Web 框架** | FastAPI 0.115 |
| **ORM** | SQLAlchemy 2.0 (异步) |
| **数据校验** | Pydantic 2.9 |
| **认证** | JWT (python-jose) |
| **定时任务** | APScheduler 3.10 |
| **爬虫** | httpx + BeautifulSoup4 + Playwright |
| **数据库** | PostgreSQL (可替换为 MySQL) |
| **缓存** | Redis |

## 项目结构
简要版
```
  app/
  ├── main.py                    # FastAPI 入口（API 网关）
  ├── config.py                  # 配置中心
  ├── api/v1/
  │   ├── auth.py                # 认证 API（注册/登录）
  │   ├── hackathons.py          # 信息大厅 API（赛事 CRUD + 筛选）
  │   ├── inspiration.py         # 灵感池 API（案例 + 注册墙）
  │   ├── recommendations.py     # 推荐 API（热度榜 + 个性化）
  │   ├── empowerment.py         # 赋能区 API（教程 + 指南）
  │   └── users.py               # 用户 API（画像 + EDM）
  ├── models/                    # SQLAlchemy ORM 模型
  ├── schemas/                   # Pydantic 请求/响应 Schema
  ├── services/                  # 业务服务层（全部 Mock 数据）
  ├── crawler/                   # 爬虫框架（Mock 实现）
  ├── db/                        # 数据库引擎
  └── middleware/                 # 认证中间件
```
详细版
```
app/
├── main.py                    # FastAPI 入口，API 网关
├── config.py                  # 配置中心（pydantic-settings）
├── api/
│   ├── deps.py                # 依赖注入（认证、分页）
│   └── v1/
│       ├── router.py          # v1 路由聚合
│       ├── auth.py            # 认证 API（注册/登录）
│       ├── hackathons.py      # 信息大厅 API（赛事 CRUD）
│       ├── inspiration.py     # 灵感池 API（案例/注册墙）
│       ├── recommendations.py # 推荐 API（热度榜/个性化）
│       ├── empowerment.py     # 赋能区 API（教程/指南）
│       └── users.py           # 用户 API（画像/EDM）
├── models/
│   ├── user.py                # 用户模型
│   ├── hackathon.py           # 黑客松赛事模型
│   ├── inspiration.py         # 灵感池内容 + 用户交互
│   └── empowerment.py         # 赋能文章模型
├── schemas/
│   ├── common.py              # 通用 Schema（分页/响应）
│   ├── user.py                # 用户请求/响应
│   ├── hackathon.py           # 赛事请求/响应
│   ├── inspiration.py         # 灵感池请求/响应
│   └── empowerment.py         # 赋能文章请求/响应
├── services/
│   ├── auth_service.py        # 认证服务（Mock）
│   ├── hackathon_service.py   # 信息大厅服务（Mock）
│   ├── inspiration_service.py # 灵感池服务（Mock）
│   ├── recommendation_service.py # 推荐引擎服务（Mock）
│   ├── empowerment_service.py # 赋能内容服务（Mock）
│   ├── edm_service.py         # EDM 邮件服务（Mock）
│   └── user_service.py        # 用户画像服务（Mock）
├── crawler/
│   ├── base.py                # 爬虫基类
│   ├── devpost.py             # Devpost 爬虫（Mock）
│   ├── mlh.py                 # MLH 爬虫（Mock）
│   ├── eventbrite.py          # Eventbrite 爬虫（Mock）
│   ├── dorahacks.py           # DoraHacks 爬虫（Mock）
│   ├── llm_processor.py       # LLM 数据清洗节点（Mock）
│   └── scheduler.py           # 爬虫调度器
├── db/
│   ├── session.py             # 数据库引擎 & 会话
│   └── base.py (via session)  # ORM 基类
└── middleware/
    └── auth_middleware.py     # 认证中间件
```

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 API 文档
open http://localhost:8000/docs
```

## API 概览

| 模块 | 路径 | 说明 |
|------|------|------|
| 认证 | `POST /api/v1/auth/register` | 用户注册 |
| 认证 | `POST /api/v1/auth/login` | 用户登录 |
| 信息大厅 | `GET /api/v1/hackathons` | 赛事列表（多维筛选） |
| 信息大厅 | `GET /api/v1/hackathons/hot` | 热度榜单 |
| 信息大厅 | `GET /api/v1/hackathons/{slug}` | 赛事详情 |
| 信息大厅 | `POST /api/v1/hackathons/{id}/click` | 外链点击记录 |
| 灵感池 | `GET /api/v1/inspiration` | 案例列表（公开摘要） |
| 灵感池 | `GET /api/v1/inspiration/{slug}` | 案例详情（注册墙） |
| 灵感池 | `POST /api/v1/inspiration/interact` | 点赞/收藏 |
| 推荐 | `GET /api/v1/recommendations/hot` | 综合热度榜 |
| 推荐 | `GET /api/v1/recommendations/for-you` | 个性化推荐 |
| 赋能 | `GET /api/v1/empowerment/vibecoding` | Vibecoding 教程 |
| 赋能 | `GET /api/v1/empowerment/guides` | 参赛指南 |
| 赋能 | `GET /api/v1/empowerment/articles` | 文章列表 |
| 用户 | `GET /api/v1/users/me` | 当前用户画像 |
| 用户 | `PUT /api/v1/users/me/tags` | 更新画像标签 |
| 用户 | `PUT /api/v1/users/me/edm-subscribe` | EDM 订阅 |
| 系统 | `GET /health` | 健康检查 |
| 系统 | `GET /api/crawler/status` | 爬虫状态 |

## 架构对应关系

本后端代码严格按照 `架构图代码.txt` 实现：

```
Layer 3 (后端业务逻辑层):
  B_Gateway  → app/main.py (FastAPI + 中间件)
  B1         → app/api/v1/auth.py + app/services/auth_service.py
  B2         → app/api/v1/hackathons.py + inspiration.py + empowerment.py
  B3         → app/api/v1/recommendations.py + app/services/recommendation_service.py
  B4         → app/services/edm_service.py

Layer 4 (数据爬取与 AI 处理层):
  D1         → app/crawler/ (base.py + scheduler.py + 各平台爬虫)
  D2         → app/crawler/llm_processor.py
  D_DB       → app/db/ + app/models/
```

## 当前状态

⚠️ **框架阶段** — 所有 Service 层使用 Mock 数据，爬虫不执行真实网络请求。
后续开发只需替换 Service 中的 Mock 实现为真实的数据库操作，以及完善爬虫的网络请求逻辑。