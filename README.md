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
| **数据库** | PostgreSQL 16 (可替换为 MySQL) |
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
  ├── services/                  # 业务服务层（数据库实现 + 部分内容 Mock）
  ├── crawler/                   # 真实爬虫、定时调度与 LLM 处理
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
│   ├── auth_service.py        # 认证服务（数据库）
│   ├── hackathon_service.py   # 信息大厅服务（数据库，仅公开筛选通过赛事）
│   ├── inspiration_service.py # 灵感池服务（Mock）
│   ├── recommendation_service.py # 推荐引擎服务（数据库赛事 + 用户画像）
│   ├── empowerment_service.py # 赋能内容服务（Mock）
│   ├── edm_service.py         # 订阅状态落库，邮件发送为 Mock
│   └── user_service.py        # 用户画像服务（数据库）
├── crawler/
│   ├── base.py                # 爬虫基类
│   ├── devpost.py 等          # 各平台真实爬虫
│   ├── llm_processor.py       # LLM 数据清洗节点
│   ├── screening_worker.py    # 赛事质量异步筛选队列
│   └── apscheduler_manager.py # 爬虫与 pending 补扫定时任务
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

# 复制并填写数据库、LLM 接口配置
cp .env.example .env

# 本地直启前应用已提交的数据库迁移；Docker 入口也只执行这一步
python -m alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 访问 API 文档
open http://localhost:8000/docs
```

### 数据库迁移流程

数据库模型发生变化后，只在开发机生成迁移文件：

```bash
python scripts/new_migration.py "add_event_category"
```

该脚本会先把本地数据库升级到当前 `head`，再执行 `--autogenerate`，最后在本地应用新迁移。生成后必须检查 `alembic/versions/` 中新文件的 `upgrade()`、`downgrade()` 和 `down_revision`，确认无误后与业务代码一起提交。

生产服务器不会生成或修改迁移文件。容器启动时只执行已经提交到 Git 并打包进镜像的：

```bash
python -m alembic upgrade head
```

不要在服务器执行 `alembic revision`，也不要把生产环境的 `alembic/versions/` 配置成可写持久化目录。

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

## 赛事入库、筛选与清洗

只有抓取成功、官方标题非空且来源 URL 有效的记录才写入 `hackathons` 表；抓取失败或
关键身份字段缺失的记录会在入库前被拒绝。通过该边界的赛事不会因质量筛选失败而丢弃。新入库赛事的
`display_status` 默认为 `PENDING`，`is_cleaned` 默认为 `false`，随后加入进程内
异步队列，由大模型并发处理：

- `PENDING`：尚未筛选，公开赛事接口不展示。
- `APPROVED`：筛选通过，接着进入大模型清洗；只有 `is_cleaned=true` 后才展示。
- `REJECTED`：筛选未通过，保留在数据库中，但公开接口不展示。

清洗只改善阅读体验：去除导航、广告、推荐文章和重复文本，整理赛事名称、摘要与
介绍。日期、奖金、规则、主办方、地点和链接等事实字段不得推测或改写；已有事实
字段不会被模型覆盖；缺失事实字段只有与 `raw_data` 中同名或明确对应的结构化
原值通过服务端校验后才补入，模型返回的标签、日期文本等错误分类不会直接入库。

服务启动时和定时任务都会扫描遗漏的 `PENDING` 赛事，以及已经 `APPROVED` 但
`is_cleaned=false` 的赛事并重新入队。单进程默认启动 2 个异步 worker，可通过
`.env` 调整：

```dotenv
LLM_API_KEY=
LLM_SCREENING_API_BASE_URL=
LLM_SCREENING_MODEL=
LLM_SCREENING_WORKERS=2
LLM_SCREENING_BATCH_SIZE=100
LLM_SCREENING_SCAN_INTERVAL_SECONDS=300
```

处理过程只输出简洁的业务日志：

```text
[Screening] 开始筛选：id=11，名称=Example Hackathon
[Screening] 模型响应：id=11，名称=Example Hackathon，模型=step-3.7-flash，stop_reason=end_turn，input_tokens=420，output_tokens=850，content_types=['thinking', 'text']，内容="{\"approved\": true, \"reason\": \"赛事信息有效\", \"confidence\": 0.95}"
[Screening] 筛选完成：id=11，名称=Example Hackathon，结果=通过
[Cleaning] 开始清洗：id=11，名称=Example Hackathon
[Cleaning] 模型响应：id=11，名称=Example Hackathon，模型=step-3.7-flash，stop_reason=end_turn，input_tokens=760，output_tokens=3500，content_types=['thinking', 'text']，内容="{\"name\": \"Example Hackathon\", ...}"
[Cleaning] 清洗完成：id=11，名称=Example Hackathon，更新字段=description,summary
```

## 当前仍在使用的 Mock 数据

| 功能 | 当前行为 | 用户侧表现 |
|------|----------|------------|
| 灵感池 | `inspiration_service.py` 内置 5 条 PGC 案例 | 列表和详情展示固定案例；点赞/收藏只修改进程内计数，服务重启后恢复 |
| 开发者赋能 | `empowerment_service.py` 内置 6 篇文章 | Vibecoding 教程、参赛指南和文章详情展示固定内容 |
| 用户收藏列表 | `GET /api/v1/users/me/bookmarks` 固定返回空数组 | 页面没有真实收藏数据 |
| EDM 邮件发送 | 订阅状态真实落库，但没有接邮件服务 | 发送操作只返回 `mock_sent`，不会真实外发邮件 |

以下模块已不是 Mock：用户注册登录、用户画像、赛事列表与详情、热度榜、个性化推荐、
爬虫抓取、LLM 数据清洗、赛事质量筛选以及后台赛事管理，均使用真实数据库或外部接口。

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

核心赛事链路已经接入真实爬虫、PostgreSQL、定时任务和 LLM 处理。当前待完善部分主要是
灵感池与开发者赋能内容持久化、用户收藏持久化，以及真实 EDM 邮件发送。
