"""
灵感池服务 — 对应架构图中的「内容调度服务 (B2)」灵感池部分
管理 PGC 精选案例的展示与注册墙拦截
"""

from datetime import datetime

# ── Mock 数据 ─────────────────────────────────────────────────────────

MOCK_INSPIRATION_ITEMS = [
    {
        "id": 1,
        "title": "【AI教育】如何用 GPT-4 打造个性化学习助手 — ETHGlobal 2025 冠军项目拆解",
        "slug": "ethglobal-2025-ai-education-champion",
        "summary": "一支来自 MIT 的三人团队，在 36 小时内用 GPT-4 + LangChain 构建了一个能根据学生知识图谱自适应生成习题的 AI 教育工具。",
        "teaser": "这不仅是技术堆砌——他们巧妙的「知识图谱+增量学习」模型设计，让项目在 200+ 参赛作品中脱颖而出。",
        "full_content": (
            "## 项目背景\n\n"
            "在 ETHGlobal 2025 黑客松中，MIT 团队「EduAI」凭借「Personalized Learning Companion」项目获得总冠军。"
            "这个项目解决了一个教育领域的核心痛点：如何为每个学生提供真正个性化的学习路径。\n\n"
            "## 技术架构\n\n"
            "1. **前端**：Next.js + Tailwind CSS，响应式设计\n"
            "2. **后端**：FastAPI + LangChain Agent\n"
            "3. **AI 引擎**：GPT-4 用于内容生成，Claude 用于学生答案评估\n"
            "4. **数据层**：Neo4j 知识图谱 + PostgreSQL\n\n"
            "## 核心创新点\n\n"
            "团队没有简单地让 AI 出题，而是构建了一个动态知识图谱：\n"
            "- 将学科知识点建模为图谱节点\n"
            "- 学生的每次答题结果更新节点间的「掌握度」权重\n"
            "- AI 根据薄弱节点自动生成针对性习题\n\n"
            "## 参赛心得\n\n"
            "队长在赛后分享提到：'我们花了前 6 个小时做需求调研和用户验证，而不是直接写代码。"
            "这个决策让我们在项目评审时有了清晰的价值主张。'\n\n"
            "## 可复用的经验\n\n"
            "1. 黑客松前 6 小时用来做需求验证，而不是写代码\n"
            "2. 选择熟悉的 AI 工具链，不要现场学习新框架\n"
            "3. 准备一个「最小可演示」的 Pitch Deck 模板"
        ),
        "source_hackathon_name": "ETHGlobal 2025",
        "source_hackathon_url": "https://ethglobal.com/events/2025",
        "team_name": "EduAI",
        "prize_won": "总冠军 + $50,000",
        "category_tags": ["AI应用", "教育科技"],
        "tech_tags": ["GPT-4", "LangChain", "Next.js", "Neo4j", "FastAPI"],
        "difficulty_level": "intermediate",
        "team_profile": {
            "size": 3,
            "roles": ["全栈工程师", "AI/ML工程师", "产品设计师"],
            "background": "MIT 计算机系研究生 + 教育学院博士生",
        },
        "cover_image_url": "https://picsum.photos/seed/eduai/800/400",
        "video_url": "https://www.youtube.com/watch?v=example1",
        "source_code_url": "https://github.com/eduai/plc",
        "demo_url": "https://eduai-demo.vercel.app",
        "like_count": 2340,
        "bookmark_count": 892,
        "view_count": 15600,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 1),
    },
    {
        "id": 2,
        "title": "【Web3 × AI】去中心化 GPU 算力交易市场 — Solana Renaissance 获奖项目复盘",
        "slug": "solana-renaissance-gpu-marketplace",
        "summary": "一个四人团队在 Solana Renaissance 黑客松中构建了去中心化 GPU 算力交易平台，让闲置 GPU 资源可以按小时出租给 AI 训练需求方。",
        "teaser": "这个项目巧妙地将 Web3 的支付/结算能力与 AI 时代的算力需求结合，展示了「区块链如何服务真实世界需求」。",
        "full_content": (
            "## 项目背景\n\n"
            "AI 训练对 GPU 算力的需求爆发式增长，但全球大量 GPU 资源处于闲置状态。"
            "「GPUGrid」团队在 Solana Renaissance 黑客松中构建了去中心化算力交易市场。\n\n"
            "## 技术架构\n\n"
            "1. **智能合约**：Solana (Rust) — 处理租赁、支付、结算、争议\n"
            "2. **算力调度**：Kubernetes + 自研 Job Scheduler\n"
            "3. **验证机制**：零知识证明验证计算完整性\n"
            "4. **前端**：React + Solana Web3.js\n\n"
            "## 商业模式\n\n"
            "- 供给端：GPU 持有者注册节点，设置价格\n"
            "- 需求端：AI 开发者提交训练任务，系统自动匹配最优节点\n"
            "- 平台抽成：每笔交易的 2%"
        ),
        "source_hackathon_name": "Solana Renaissance Hackathon",
        "source_hackathon_url": "https://solana.com/renaissance",
        "team_name": "GPUGrid",
        "prize_won": "DePIN 赛道一等奖 + $75,000",
        "category_tags": ["Web3", "AI应用", "基础设施"],
        "tech_tags": ["Rust", "Solana", "React", "Kubernetes", "ZK Proofs"],
        "difficulty_level": "advanced",
        "team_profile": {
            "size": 4,
            "roles": ["区块链工程师", "后端工程师", "前端工程师", "产品经理"],
            "background": "2名Web3开发者 + 1名云计算工程师 + 1名MBA",
        },
        "cover_image_url": "https://picsum.photos/seed/gpugrid/800/400",
        "video_url": None,
        "source_code_url": "https://github.com/gpugrid/solana",
        "demo_url": "https://gpugrid.io",
        "like_count": 1890,
        "bookmark_count": 654,
        "view_count": 12300,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 10),
    },
    {
        "id": 3,
        "title": "【新手友好】一个非技术背景团队如何用 Vibecoding 在黑客松中获奖",
        "slug": "non-tech-team-vibecoding-success",
        "summary": "三位来自商学院的「非技术」参赛者，利用 Cursor + GPT-4 + Replit 在 48 小时内构建了一款校园二手交易小程序，并获得「最佳产品设计奖」。",
        "teaser": "零代码基础？没问题。这个案例告诉你：在 AI 时代，产品 sense 和执行力比编码能力更重要。",
        "full_content": (
            "## 团队背景\n\n"
            "三名成员全部来自商学院，没有任何软件开发经验。他们的参赛项目是「CampusSwap」——一个校园二手交易微信小程序。\n\n"
            "## 使用的 Vibecoding 工具\n\n"
            "1. **Cursor**：主力代码编辑器，用自然语言描述需求，AI 生成代码\n"
            "2. **GPT-4**：架构设计咨询 + 调试 + 文案生成\n"
            "3. **Replit**：快速原型验证\n"
            "4. **Midjourney**：UI 素材和产品海报生成\n\n"
            "## 48 小时时间线\n\n"
            "- **0-4h**：确定产品方向，用 GPT-4 生成 PRD 和用户故事\n"
            "- **4-12h**：用 Cursor 搭建小程序前端页面\n"
            "- **12-24h**：搭建后端 API（Node.js + SQLite）\n"
            "- **24-36h**：集成微信支付 + 地图定位\n"
            "- **36-44h**：测试 + 修复 Bug\n"
            "- **44-48h**：准备 Pitch Deck + 演示视频\n\n"
            "## 关键学习\n\n"
            "1. AI 工具让「想法→产品」的路径缩短了 90%\n"
            "2. 产品思维 > 技术能力：评委更在意你解决了什么问题\n"
            "3. 善用 AI 做用户调研和竞品分析"
        ),
        "source_hackathon_name": "HackUST 2025",
        "source_hackathon_url": "https://hackust.org",
        "team_name": "CampusSwap",
        "prize_won": "最佳产品设计奖 + $5,000",
        "category_tags": ["生活方式", "教育科技", "Vibecoding"],
        "tech_tags": ["Cursor", "GPT-4", "Replit", "微信小程序", "Node.js"],
        "difficulty_level": "beginner",
        "team_profile": {
            "size": 3,
            "roles": ["产品经理", "UI/UX", "市场运营"],
            "background": "全部来自商学院（非技术背景）",
        },
        "cover_image_url": "https://picsum.photos/seed/campusswap/800/400",
        "video_url": "https://www.bilibili.com/video/example3",
        "source_code_url": "https://github.com/campusswap/app",
        "demo_url": None,
        "like_count": 5670,
        "bookmark_count": 2340,
        "view_count": 35000,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 4, 15),
    },
    {
        "id": 4,
        "title": "【开发者工具】AI 驱动的代码审查助手 — DoraHacks AI 赛道冠军",
        "slug": "ai-code-review-assistant-dorahacks",
        "summary": "一个两人团队构建的 AI 代码审查工具，可以自动分析 PR 中的潜在 Bug、安全漏洞和性能问题，并给出修复建议。",
        "teaser": "这个工具已经开源并在 GitHub 上获得了 3k+ Star。他们证明了：黑客松项目可以成为真正的产品。",
        "full_content": (
            "## 项目起源\n\n"
            "两位开发者在日常工作中发现代码审查占用了大量时间，于是决定用 AI 自动化这个过程。"
            "在 DoraHacks AI 赛道中，他们用 48 小时构建了「CodeSentinel」的原型。\n\n"
            "## 技术栈\n\n"
            "1. **核心引擎**：Claude API + 自定义 Prompt Chain\n"
            "2. **后端**：Python FastAPI + Celery\n"
            "3. **GitHub 集成**：GitHub App + Webhook\n"
            "4. **前端**：React + Monaco Editor\n\n"
            "## 从黑客松到产品\n\n"
            "赛后他们持续迭代，3 个月内完成了：\n"
            "- GitHub Marketplace 上架\n"
            "- 支持 15+ 编程语言\n"
            "- 获得种子轮融资\n"
            "- 3k+ GitHub Stars"
        ),
        "source_hackathon_name": "DoraHacks AI Hackathon 2025",
        "source_hackathon_url": "https://dorahacks.io",
        "team_name": "CodeSentinel",
        "prize_won": "AI 赛道冠军 + $30,000",
        "category_tags": ["开发者工具", "AI应用", "SaaS"],
        "tech_tags": ["Claude API", "Python", "FastAPI", "React", "GitHub API"],
        "difficulty_level": "advanced",
        "team_profile": {
            "size": 2,
            "roles": ["全栈工程师", "AI/ML工程师"],
            "background": "两位前 Google 工程师",
        },
        "cover_image_url": "https://picsum.photos/seed/codesentinel/800/400",
        "video_url": "https://www.youtube.com/watch?v=example4",
        "source_code_url": "https://github.com/codesentinel/app",
        "demo_url": "https://codesentinel.dev",
        "like_count": 3200,
        "bookmark_count": 1200,
        "view_count": 21000,
        "is_published": True,
        "is_featured": False,
        "created_at": datetime(2026, 5, 18),
    },
    {
        "id": 5,
        "title": "【游戏开发】用 AI 生成 3D 游戏世界 — 2 人团队 48 小时打造开放世界原型",
        "slug": "ai-generated-3d-game-world",
        "summary": "使用 Meshy.ai + Cursor + Unity，在 48 小时内生成一个完整的 3D 开放世界游戏原型，包括地形、建筑、NPC 和对话系统。",
        "teaser": "传统上需要数月开发的 3D 游戏世界，现在用 AI 工具 48 小时就能完成。这就是 Vibecoding 在游戏开发中的力量。",
        "full_content": (
            "## 项目概述\n\n"
            "项目「DreamWorld」展示了 AI 如何彻底改变游戏开发流程。两位开发者利用了最新的 AI 3D 资产生成工具，"
            "在 48 小时内创建了一个完整的开放世界游戏原型。\n\n"
            "## 使用的 AI 工具链\n\n"
            "1. **Meshy.ai**：3D 模型和纹理生成\n"
            "2. **Cursor**：游戏逻辑代码生成\n"
            "3. **GPT-4**：NPC 对话系统和剧情生成\n"
            "4. **Unity**：游戏引擎集成\n"
            "5. **Blockade Labs**：天空盒生成\n\n"
            "## 成果\n\n"
            "- 5 平方公里可探索区域\n"
            "- 20+ 种 AI 生成的建筑和道具\n"
            "- 10 个有性格的 NPC（AI 驱动对话）\n"
            "- 完整的昼夜循环系统"
        ),
        "source_hackathon_name": "Global Game Jam 2026",
        "source_hackathon_url": "https://globalgamejam.org",
        "team_name": "DreamWorld",
        "prize_won": "最佳创新奖",
        "category_tags": ["游戏开发", "Vibecoding", "AI应用"],
        "tech_tags": ["Unity", "Meshy.ai", "Cursor", "GPT-4", "C#"],
        "difficulty_level": "intermediate",
        "team_profile": {
            "size": 2,
            "roles": ["游戏开发者", "3D艺术家"],
            "background": "独立游戏开发者 + 数字艺术家",
        },
        "cover_image_url": "https://picsum.photos/seed/dreamworld/800/400",
        "video_url": "https://www.youtube.com/watch?v=example5",
        "source_code_url": "https://github.com/dreamworld/game",
        "demo_url": "https://dreamworld.itch.io",
        "like_count": 4100,
        "bookmark_count": 1560,
        "view_count": 28000,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 22),
    },
]


class InspirationService:
    """灵感池服务（Mock 实现）"""

    @staticmethod
    async def list_items(
        category_tags: list[str] | None = None,
        tech_tags: list[str] | None = None,
        difficulty_level: str | None = None,
        keyword: str | None = None,
        sort_by: str = "created_at",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """获取灵感池内容列表"""
        results = [dict(item) for item in MOCK_INSPIRATION_ITEMS if item["is_published"]]

        # ── 筛选 ──
        if category_tags:
            results = [
                r for r in results
                if r.get("category_tags") and any(t in r["category_tags"] for t in category_tags)
            ]
        if tech_tags:
            results = [
                r for r in results
                if r.get("tech_tags") and any(t in r["tech_tags"] for t in tech_tags)
            ]
        if difficulty_level:
            results = [r for r in results if r.get("difficulty_level") == difficulty_level]
        if keyword:
            kw = keyword.lower()
            results = [
                r for r in results
                if kw in r["title"].lower()
                or (r.get("summary") and kw in r["summary"].lower())
            ]

        # ── 排序 ──
        if sort_by == "like_count":
            results.sort(key=lambda r: r["like_count"], reverse=True)
        elif sort_by == "view_count":
            results.sort(key=lambda r: r["view_count"], reverse=True)
        else:
            results.sort(key=lambda r: r["created_at"], reverse=True)

        total = len(results)
        start = (page - 1) * page_size
        items = results[start:start + page_size]

        return items, total

    @staticmethod
    async def get_item(slug: str) -> dict | None:
        """获取灵感内容详情"""
        for item in MOCK_INSPIRATION_ITEMS:
            if item["slug"] == slug and item["is_published"]:
                return dict(item)
        return None

    @staticmethod
    async def get_public_summary(slug: str) -> dict | None:
        """获取公开摘要（游客可见，不含 full_content）"""
        item = await InspirationService.get_item(slug)
        if item:
            public = dict(item)
            public.pop("full_content", None)
            public.pop("video_url", None)
            public.pop("source_code_url", None)
            public.pop("demo_url", None)
            return public
        return None

    @staticmethod
    async def record_interaction(user_id: int, item_id: int, interaction_type: str) -> dict:
        """记录用户交互（点赞/收藏）"""
        for item in MOCK_INSPIRATION_ITEMS:
            if item["id"] == item_id:
                if interaction_type == "like":
                    item["like_count"] += 1
                elif interaction_type == "bookmark":
                    item["bookmark_count"] += 1
                return {"user_id": user_id, "item_id": item_id, "interaction_type": interaction_type}
        return {}


inspiration_service = InspirationService()