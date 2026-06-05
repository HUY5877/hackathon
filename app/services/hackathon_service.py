"""
信息大厅服务 — 对应架构图中的「内容调度服务 (B2)」
管理黑客松赛事数据的查询、筛选与交互
"""

from datetime import datetime, timedelta

from app.services.auth_service import MOCK_USERS

# ── Mock 数据 ─────────────────────────────────────────────────────────

MOCK_HACKATHONS = [
    {
        "id": 1,
        "name": "ETHGlobal Sydney 2026",
        "slug": "ethglobal-sydney-2026",
        "description": (
            "ETHGlobal 是全球最大的以太坊黑客松组织方之一。本次悉尼站将汇聚来自亚太地区的 "
            "顶尖 Web3 开发者，围绕 DeFi、NFT、DAO、Layer2 等赛道进行 48 小时的创意冲刺。"
            "无论你是 Solidity 老手还是 Web3 新手，这里都有适合你的赛道和导师资源。"
        ),
        "summary": "ETHGlobal 悉尼站 —— 亚太地区最大的 Web3 黑客松，$150,000+ 奖金池。",
        "registration_start": datetime(2026, 6, 1),
        "registration_end": datetime(2026, 7, 15),
        "event_start": datetime(2026, 7, 25),
        "event_end": datetime(2026, 7, 27),
        "status": "registering",
        "mode": "offline",
        "track_tags": ["Web3", "DeFi", "NFT", "Layer2", "DAO"],
        "tech_tags": ["Solidity", "Ethereum", "React", "Rust"],
        "prize_pool": "$150,000 USD",
        "prize_pool_usd": 150000.0,
        "expected_participants": 500,
        "location": "Sydney, Australia",
        "country": "Australia",
        "city": "Sydney",
        "source_url": "https://ethglobal.com/events/sydney",
        "source_platform": "ethglobal",
        "registration_url": "https://ethglobal.com/events/sydney/register",
        "organizer": "ETHGlobal",
        "sponsors": ["Ethereum Foundation", "Polygon", "Arbitrum", "Optimism"],
        "is_verified": True,
        "llm_confidence": 0.95,
        "view_count": 3240,
        "external_click_count": 856,
        "created_at": datetime(2026, 5, 10),
    },
    {
        "id": 2,
        "name": "AI Hackathon 2026 — 生成式AI创新应用大赛",
        "slug": "ai-hackathon-2026-genai",
        "description": (
            "聚焦生成式 AI 技术的创新应用大赛。参赛者需使用 GPT-4、Claude、Gemini 等 "
            "大模型 API，在 36 小时内打造具有商业潜力的 AI 原生应用。赛道涵盖 AI Agent、"
            "多模态应用、AI + 垂直行业（医疗/教育/金融/法律）。"
        ),
        "summary": "36 小时打造 AI 原生应用！$80,000 奖金 + 投资机构直通车机会。",
        "registration_start": datetime(2026, 5, 15),
        "registration_end": datetime(2026, 7, 31),
        "event_start": datetime(2026, 8, 10),
        "event_end": datetime(2026, 8, 12),
        "status": "registering",
        "mode": "hybrid",
        "track_tags": ["AI应用", "生成式AI", "AI Agent", "多模态"],
        "tech_tags": ["Python", "TypeScript", "OpenAI API", "LangChain"],
        "prize_pool": "¥600,000 CNY",
        "prize_pool_usd": 82000.0,
        "expected_participants": 800,
        "location": "北京 + 线上",
        "country": "China",
        "city": "Beijing",
        "source_url": "https://example.com/ai-hackathon-2026",
        "source_platform": "huodongxing",
        "registration_url": "https://example.com/ai-hackathon-2026/register",
        "organizer": "AI社区 & 某头部VC",
        "sponsors": ["OpenAI", "Anthropic", "Google Cloud", "阿里云"],
        "is_verified": True,
        "llm_confidence": 0.92,
        "view_count": 5670,
        "external_click_count": 1203,
        "created_at": datetime(2026, 5, 8),
    },
    {
        "id": 3,
        "name": "DoraHacks Quantum Leap — 量子计算黑客松",
        "slug": "dorahacks-quantum-leap-2026",
        "description": (
            "DoraHacks 联合 IBM Quantum 举办的首届量子计算黑客松。探索量子机器学习、"
            "量子密码学、量子模拟等前沿方向。无需量子物理背景，大赛提供完整的入门工作坊。"
        ),
        "summary": "量子计算 × 黑客松！DoraHacks × IBM Quantum 联合呈现，$50,000 奖金。",
        "registration_start": datetime(2026, 6, 15),
        "registration_end": datetime(2026, 8, 1),
        "event_start": datetime(2026, 8, 15),
        "event_end": datetime(2026, 8, 17),
        "status": "upcoming",
        "mode": "online",
        "track_tags": ["量子计算", "AI", "密码学", "模拟"],
        "tech_tags": ["Qiskit", "Python", "Cirq", "PennyLane"],
        "prize_pool": "$50,000 USD",
        "prize_pool_usd": 50000.0,
        "expected_participants": 300,
        "location": "线上",
        "country": "Global",
        "city": None,
        "source_url": "https://dorahacks.io/hackathon/quantum-leap",
        "source_platform": "dorahacks",
        "registration_url": "https://dorahacks.io/hackathon/quantum-leap/register",
        "organizer": "DoraHacks × IBM Quantum",
        "sponsors": ["IBM Quantum", "AWS Braket"],
        "is_verified": True,
        "llm_confidence": 0.88,
        "view_count": 1890,
        "external_click_count": 423,
        "created_at": datetime(2026, 5, 25),
    },
    {
        "id": 4,
        "name": "HackUST 2026 — 港科大创客马拉松",
        "slug": "hackust-2026",
        "description": (
            "香港科技大学年度创客马拉松，面向亚太区所有高校学生。不设主题限制，"
            "鼓励跨学科团队自由创新。往届项目涵盖教育科技、智慧城市、健康科技、"
            "可持续发展等领域。"
        ),
        "summary": "港科大年度创客马拉松！不限主题、不限技术栈，$25,000 奖金等你来挑战。",
        "registration_start": datetime(2026, 7, 1),
        "registration_end": datetime(2026, 9, 1),
        "event_start": datetime(2026, 9, 20),
        "event_end": datetime(2026, 9, 22),
        "status": "upcoming",
        "mode": "offline",
        "track_tags": ["教育科技", "智慧城市", "健康科技", "可持续发展", "开发者工具"],
        "tech_tags": ["不限"],
        "prize_pool": "HK$200,000",
        "prize_pool_usd": 25500.0,
        "expected_participants": 400,
        "location": "香港科技大学",
        "country": "China",
        "city": "Hong Kong",
        "source_url": "https://hackust.org",
        "source_platform": "hackust",
        "registration_url": "https://hackust.org/register",
        "organizer": "HKUST Entrepreneurship Center",
        "sponsors": ["HKSTP", "Cyberport", "Google"],
        "is_verified": False,
        "llm_confidence": 0.85,
        "view_count": 1560,
        "external_click_count": 312,
        "created_at": datetime(2026, 5, 28),
    },
    {
        "id": 5,
        "name": "MLH Global Hack Week 2026 — Cloud",
        "slug": "mlh-global-hack-week-cloud-2026",
        "description": (
            "Major League Hacking 举办的全球线上黑客周，本期主题为 Cloud。"
            "为期一周的线上黑客松，每天有技术工作坊、导师 Office Hour 和趣味小挑战。"
            "适合所有技能水平的开发者参与。"
        ),
        "summary": "MLH 全球黑客周（云主题）！为期一周的线上黑客松，新手友好、奖品丰富。",
        "registration_start": datetime(2026, 6, 1),
        "registration_end": datetime(2026, 7, 8),
        "event_start": datetime(2026, 7, 14),
        "event_end": datetime(2026, 7, 21),
        "status": "registering",
        "mode": "online",
        "track_tags": ["Cloud", "Serverless", "DevOps", "API"],
        "tech_tags": ["AWS", "Docker", "Kubernetes", "Terraform", "Python"],
        "prize_pool": "$10,000 USD + 周边礼品",
        "prize_pool_usd": 10000.0,
        "expected_participants": 2000,
        "location": "线上",
        "country": "Global",
        "city": None,
        "source_url": "https://ghw.mlh.io/events/cloud",
        "source_platform": "mlh",
        "registration_url": "https://ghw.mlh.io/events/cloud/register",
        "organizer": "Major League Hacking (MLH)",
        "sponsors": ["AWS", "GitHub", "DigitalOcean", "Twilio"],
        "is_verified": True,
        "llm_confidence": 0.93,
        "view_count": 8900,
        "external_click_count": 2340,
        "created_at": datetime(2026, 5, 5),
    },
    {
        "id": 6,
        "name": "Solana Renaissance Hackathon",
        "slug": "solana-renaissance-hackathon-2026",
        "description": (
            "Solana 基金会主办的全球黑客松，聚焦 Solana 生态的创新应用。"
            "赛道包括 DeFi、支付、游戏、DePIN、AI x Crypto。"
            "总奖金池超过 $1,000,000 USD（含生态 Grant 和种子投资）。"
        ),
        "summary": "Solana 生态最大黑客松！$1,000,000+ 奖金池，DeFi / 游戏 / DePIN / AI×Crypto 多赛道。",
        "registration_start": datetime(2026, 5, 1),
        "registration_end": datetime(2026, 7, 1),
        "event_start": datetime(2026, 6, 1),
        "event_end": datetime(2026, 7, 15),
        "status": "ongoing",
        "mode": "online",
        "track_tags": ["Web3", "DeFi", "Gaming", "DePIN", "AIxCrypto"],
        "tech_tags": ["Rust", "Solana", "Anchor", "React", "TypeScript"],
        "prize_pool": "$1,000,000+ USD",
        "prize_pool_usd": 1000000.0,
        "expected_participants": 3000,
        "location": "线上",
        "country": "Global",
        "city": None,
        "source_url": "https://solana.com/renaissance",
        "source_platform": "solana",
        "registration_url": "https://solana.com/renaissance/register",
        "organizer": "Solana Foundation",
        "sponsors": ["Solana Ventures", "Jump Crypto", "a16z Crypto"],
        "is_verified": True,
        "llm_confidence": 0.96,
        "view_count": 12500,
        "external_click_count": 4100,
        "created_at": datetime(2026, 4, 20),
    },
]


class HackathonService:
    """信息大厅服务（Mock 实现）"""

    @staticmethod
    async def list_hackathons(
        status: str | None = None,
        mode: str | None = None,
        track_tags: list[str] | None = None,
        tech_tags: list[str] | None = None,
        country: str | None = None,
        keyword: str | None = None,
        sort_by: str = "event_start",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """获取黑客松列表（支持多维筛选）"""
        results = [dict(h) for h in MOCK_HACKATHONS]

        # ── 筛选 ──
        if status:
            results = [h for h in results if h["status"] == status]
        if mode:
            results = [h for h in results if h["mode"] == mode]
        if track_tags:
            results = [
                h for h in results
                if h.get("track_tags") and any(t in h["track_tags"] for t in track_tags)
            ]
        if tech_tags:
            results = [
                h for h in results
                if h.get("tech_tags") and any(t in h["tech_tags"] for t in tech_tags)
            ]
        if country:
            results = [h for h in results if h.get("country") == country]
        if keyword:
            kw = keyword.lower()
            results = [
                h for h in results
                if kw in h["name"].lower()
                or (h.get("summary") and kw in h["summary"].lower())
                or (h.get("description") and kw in h["description"].lower())
            ]

        # ── 排序 ──
        if sort_by == "prize_pool_usd":
            results.sort(key=lambda h: h.get("prize_pool_usd") or 0, reverse=True)
        elif sort_by == "view_count":
            results.sort(key=lambda h: h["view_count"], reverse=True)
        elif sort_by == "created_at":
            results.sort(key=lambda h: h["created_at"], reverse=True)
        else:  # event_start
            results.sort(key=lambda h: h.get("event_start") or datetime.max)

        total = len(results)

        # ── 分页 ──
        start = (page - 1) * page_size
        end = start + page_size
        items = results[start:end]

        return items, total

    @staticmethod
    async def get_hackathon(slug: str) -> dict | None:
        """获取黑客松详情"""
        for h in MOCK_HACKATHONS:
            if h["slug"] == slug:
                return dict(h)
        return None

    @staticmethod
    async def record_external_click(hackathon_id: int) -> dict:
        """记录外链点击（Mock: 永远成功）"""
        for h in MOCK_HACKATHONS:
            if h["id"] == hackathon_id:
                h["external_click_count"] += 1
                return {"click_id": h["external_click_count"], "hackathon_id": hackathon_id}
        return {"click_id": 0, "hackathon_id": hackathon_id}

    @staticmethod
    async def get_hot_list(limit: int = 5) -> list[dict]:
        """获取综合热度榜单"""
        sorted_hackathons = sorted(MOCK_HACKATHONS, key=lambda h: h["view_count"], reverse=True)
        return [dict(h) for h in sorted_hackathons[:limit]]


hackathon_service = HackathonService()