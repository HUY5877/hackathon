"""
开发者赋能服务 — 对应架构图中的「内容调度服务 (B2)」赋能区部分
管理 Vibecoding 教程和黑客松参赛指南
"""

from datetime import datetime

# ── Mock 数据 ─────────────────────────────────────────────────────────

MOCK_EMPOWERMENT_ARTICLES = [
    {
        "id": 1,
        "title": "【Cursor 入门】从零到一：用自然语言构建你的第一个 Web 应用",
        "slug": "cursor-from-zero-to-first-webapp",
        "content_type": "vibecoding",
        "sub_category": "cursor",
        "summary": "不需要写一行代码！本教程将带你用 Cursor 的 AI 对话功能，在 30 分钟内搭建一个完整的 Todo List Web 应用。",
        "full_content": (
            "## 前置准备\n\n"
            "1. 下载安装 [Cursor](https://cursor.sh)\n"
            "2. 注册账号（免费版即可）\n\n"
            "## 步骤一：用自然语言描述需求\n\n"
            "在 Cursor 的 AI 对话中直接输入：\n"
            "'帮我创建一个 Todo List 应用，使用 React + TypeScript，支持添加、删除、标记完成和筛选功能。'\n\n"
            "## 步骤二：AI 生成代码\n\n"
            "Cursor 会自动生成完整的项目结构和代码...\n\n"
            "## 步骤三：迭代优化\n\n"
            "继续用自然语言提出修改需求...\n\n"
            "## 关键技巧\n\n"
            "1. 描述越具体，AI 生成的代码越准确\n"
            "2. 善用 Cursor 的 'Apply' 功能一键应用修改\n"
            "3. 遇到 Bug 直接粘贴报错信息给 AI"
        ),
        "difficulty_level": "beginner",
        "estimated_read_time": 15,
        "tags": ["Cursor", "React", "TypeScript", "Web开发", "新手入门"],
        "cover_image_url": "https://picsum.photos/seed/cursor-tutorial/800/400",
        "video_url": "https://www.youtube.com/watch?v=cursor-tutorial",
        "external_url": None,
        "view_count": 12500,
        "like_count": 890,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 1),
        "updated_at": datetime(2026, 5, 1),
    },
    {
        "id": 2,
        "title": "【GitHub Copilot 进阶】用 Copilot 加速黑客松 MVP 开发的 10 个技巧",
        "slug": "copilot-advanced-hackathon-mvp-tips",
        "content_type": "vibecoding",
        "sub_category": "copilot",
        "summary": "掌握这些 Copilot 高级技巧，在黑客松中让你的编码速度提升 3 倍。包括代码生成、测试编写、文档生成和重构。",
        "full_content": (
            "## 技巧一：用注释作为 Prompt\n\n"
            "在 Copilot 中，写好注释等于写好 Prompt。示例：\n"
            "```python\n"
            "# 实现一个函数，接收用户标签列表，返回匹配度最高的 5 个黑客松赛事\n"
            "```\n\n"
            "## 技巧二：先生成测试，再生成实现\n\n"
            "用 Copilot 生成测试用例，然后基于测试用例生成实现代码...\n\n"
            "## 技巧三：利用 Copilot Chat 进行代码审查\n\n"
            "在提交前，用 Copilot Chat 检查代码中的潜在问题...\n\n"
            "## ...更多技巧"
        ),
        "difficulty_level": "intermediate",
        "estimated_read_time": 20,
        "tags": ["GitHub Copilot", "MVP", "效率提升", "黑客松"],
        "cover_image_url": "https://picsum.photos/seed/copilot-tips/800/400",
        "video_url": "https://www.youtube.com/watch?v=copilot-tips",
        "external_url": None,
        "view_count": 8900,
        "like_count": 670,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 5),
        "updated_at": datetime(2026, 5, 5),
    },
    {
        "id": 3,
        "title": "【ChatGPT 实战】用 GPT-4 生成完整的黑客松 Pitch Deck 大纲",
        "slug": "chatgpt-pitch-deck-generation",
        "content_type": "vibecoding",
        "sub_category": "chatgpt",
        "summary": "学会用 ChatGPT 快速生成专业的 Pitch Deck 大纲、演讲脚本和演示文稿，让你的黑客松路演脱颖而出。",
        "full_content": (
            "## 为什么要用 AI 辅助 Pitch Deck？\n\n"
            "在黑客松中，最后 4 小时的 Pitch 准备往往决定成败。AI 可以帮你：\n"
            "- 快速生成结构化大纲\n"
            "- 优化问题陈述和价值主张\n"
            "- 生成数据可视化建议\n\n"
            "## Prompt 模板\n\n"
            "```\n"
            "你是一个资深的产品经理和投资人。我正在参加一个黑客松，"
            "项目是 [项目名称]，解决 [核心问题]。\n"
            "请帮我生成一个 3 分钟的 Pitch Deck 大纲，包含以下部分：\n"
            "1. 问题陈述\n"
            "2. 解决方案\n"
            "3. 市场机会\n"
            "4. 技术亮点\n"
            "5. 商业模式\n"
            "6. 团队介绍\n"
            "```"
        ),
        "difficulty_level": "beginner",
        "estimated_read_time": 12,
        "tags": ["ChatGPT", "Pitch Deck", "路演", "提示词工程"],
        "cover_image_url": "https://picsum.photos/seed/pitch-deck/800/400",
        "video_url": "https://www.youtube.com/watch?v=pitch-deck-tutorial",
        "external_url": None,
        "view_count": 15600,
        "like_count": 1200,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 5, 8),
        "updated_at": datetime(2026, 5, 8),
    },
    {
        "id": 4,
        "title": "黑客松组队与参赛全流程科普：从报名到路演的一站式指南",
        "slug": "hackathon-complete-guide-from-registration-to-pitch",
        "content_type": "guide",
        "sub_category": "process",
        "summary": "第一次参加黑客松？这份指南覆盖了赛前准备、组队策略、项目选题、开发节奏、Pitch 准备和赛后跟进的全部环节。",
        "full_content": (
            "## 第一阶段：赛前准备（比赛前 1-2 周）\n\n"
            "### 1.1 选择适合自己的比赛\n"
            "- 新手优先选择有「新手友好」标签或提供工作坊的赛事\n"
            "- 关注比赛主题是否与你的技术栈匹配\n"
            "- 查看往届获奖项目，评估难度\n\n"
            "### 1.2 组队策略\n"
            "- 理想团队配置：1 产品 + 1 设计 + 2-3 开发\n"
            "- 建议在比赛官方 Discord/Slack 中提前认识队友\n"
            "- 明确分工和沟通方式\n\n"
            "## 第二阶段：比赛进行中\n\n"
            "### 2.1 前 4 小时：选题与验证\n"
            "### 2.2 4-36 小时：核心开发\n"
            "### 2.3 最后 12 小时：完善与 Pitch 准备\n\n"
            "## 第三阶段：赛后\n\n"
            "### 3.1 项目开源\n"
            "### 3.2 持续迭代\n"
            "### 3.3 社区建设"
        ),
        "difficulty_level": "beginner",
        "estimated_read_time": 25,
        "tags": ["黑客松入门", "组队", "全流程", "参赛指南"],
        "cover_image_url": "https://picsum.photos/seed/hackathon-guide/800/400",
        "video_url": None,
        "external_url": None,
        "view_count": 22000,
        "like_count": 1800,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 4, 20),
        "updated_at": datetime(2026, 4, 20),
    },
    {
        "id": 5,
        "title": "如何撰写并制作高分路演 PPT（Pitch Deck）—— 评审视角的完整指南",
        "slug": "how-to-create-winning-pitch-deck",
        "content_type": "guide",
        "sub_category": "pitch_deck",
        "summary": "从评审的角度拆解：什么样的 Pitch Deck 能拿高分？包含真实获奖案例的幻灯片分析和可复用的模板。",
        "full_content": (
            "## 评审在 3 分钟内关注什么？\n\n"
            "1. **问题是否真实且重要**（30 秒）\n"
            "2. **解决方案是否足够创新**（30 秒）\n"
            "3. **Demo 是否可运行**（60 秒）\n"
            "4. **团队是否靠谱**（30 秒）\n"
            "5. **商业潜力**（30 秒）\n\n"
            "## 幻灯片结构（10 页黄金模板）\n\n"
            "1. 封面（标题 + 一句话描述）\n"
            "2. 问题\n"
            "3. 解决方案\n"
            "4. 为什么现在？（时机）\n"
            "5. 产品 Demo（截图/GIF）\n"
            "6. 技术架构\n"
            "7. 市场机会\n"
            "8. 商业模式\n"
            "9. 团队\n"
            "10. 致谢 + 联系方式\n\n"
            "## 常见错误\n\n"
            "- ❌ 问题描述太抽象\n"
            "- ❌ 没有 Demo（只有 PPT 是致命伤）\n"
            "- ❌ 技术栈描述过于详细\n"
            "- ❌ 团队介绍太谦虚"
        ),
        "difficulty_level": "intermediate",
        "estimated_read_time": 18,
        "tags": ["Pitch Deck", "路演", "PPT", "评审视角"],
        "cover_image_url": "https://picsum.photos/seed/pitch-deck-guide/800/400",
        "video_url": "https://www.youtube.com/watch?v=pitch-deck-guide",
        "external_url": None,
        "view_count": 18000,
        "like_count": 1500,
        "is_published": True,
        "is_featured": True,
        "created_at": datetime(2026, 4, 25),
        "updated_at": datetime(2026, 4, 25),
    },
    {
        "id": 6,
        "title": "【Windsurf 入门】用 AI IDE 在 1 小时内构建一个完整的 REST API",
        "slug": "windsurf-build-rest-api-in-1-hour",
        "content_type": "vibecoding",
        "sub_category": "general",
        "summary": "使用 Windsurf（Codeium）的 AI 功能，从零搭建一个包含认证、CRUD 和分页的 REST API 后端服务。",
        "full_content": (
            "## 为什么选择 Windsurf？\n\n"
            "Windsurf 是 Codeium 推出的 AI IDE，特点是：\n"
            "- 上下文感知能力更强\n"
            "- 多文件编辑更流畅\n"
            "- 免费版功能丰富\n\n"
            "## 本教程目标\n\n"
            "在 1 小时内用 Python FastAPI 构建一个完整的 Todo API...\n\n"
            "## 步骤详解\n\n"
            "### 1. 项目初始化（5 分钟）\n"
            "### 2. 数据模型设计（10 分钟）\n"
            "### 3. API 路由实现（20 分钟）\n"
            "### 4. 认证中间件（15 分钟）\n"
            "### 5. 测试与调试（10 分钟）"
        ),
        "difficulty_level": "beginner",
        "estimated_read_time": 15,
        "tags": ["Windsurf", "FastAPI", "Python", "API", "后端开发"],
        "cover_image_url": "https://picsum.photos/seed/windsurf-api/800/400",
        "video_url": "https://www.youtube.com/watch?v=windsurf-api",
        "external_url": None,
        "view_count": 6700,
        "like_count": 450,
        "is_published": True,
        "is_featured": False,
        "created_at": datetime(2026, 5, 15),
        "updated_at": datetime(2026, 5, 15),
    },
]


class EmpowermentService:
    """开发者赋能服务（Mock 实现）"""

    @staticmethod
    async def list_articles(
        content_type: str | None = None,
        sub_category: str | None = None,
        difficulty_level: str | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
        sort_by: str = "created_at",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """获取赋能文章列表"""
        results = [dict(a) for a in MOCK_EMPOWERMENT_ARTICLES if a["is_published"]]

        if content_type:
            results = [r for r in results if r["content_type"] == content_type]
        if sub_category:
            results = [r for r in results if r.get("sub_category") == sub_category]
        if difficulty_level:
            results = [r for r in results if r.get("difficulty_level") == difficulty_level]
        if tags:
            results = [
                r for r in results
                if r.get("tags") and any(t in r["tags"] for t in tags)
            ]
        if keyword:
            kw = keyword.lower()
            results = [
                r for r in results
                if kw in r["title"].lower()
                or (r.get("summary") and kw in r["summary"].lower())
            ]

        if sort_by == "view_count":
            results.sort(key=lambda r: r["view_count"], reverse=True)
        elif sort_by == "like_count":
            results.sort(key=lambda r: r["like_count"], reverse=True)
        else:
            results.sort(key=lambda r: r["created_at"], reverse=True)

        total = len(results)
        start = (page - 1) * page_size
        items = results[start:start + page_size]

        return items, total

    @staticmethod
    async def get_article(slug: str) -> dict | None:
        """获取文章详情"""
        for article in MOCK_EMPOWERMENT_ARTICLES:
            if article["slug"] == slug and article["is_published"]:
                return dict(article)
        return None

    @staticmethod
    async def get_vibecoding_articles(limit: int = 5) -> list[dict]:
        """获取 Vibecoding 教程列表"""
        articles = [
            dict(a) for a in MOCK_EMPOWERMENT_ARTICLES
            if a["content_type"] == "vibecoding" and a["is_published"]
        ]
        articles.sort(key=lambda a: a["created_at"], reverse=True)
        return articles[:limit]

    @staticmethod
    async def get_guide_articles(limit: int = 5) -> list[dict]:
        """获取参赛指南列表"""
        articles = [
            dict(a) for a in MOCK_EMPOWERMENT_ARTICLES
            if a["content_type"] == "guide" and a["is_published"]
        ]
        articles.sort(key=lambda a: a["created_at"], reverse=True)
        return articles[:limit]


empowerment_service = EmpowermentService()