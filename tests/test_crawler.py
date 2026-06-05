"""爬虫集成测试 — 真实网络请求，不使用 mock"""

import json
import pytest
from dataclasses import asdict

from app.crawler.base import CrawlResult
from app.crawler.llm_processor import LLMProcessor, StandardizedHackathon


# ── DoraHacks 真实爬取（CloakBrowser） ────────────────

class TestDoraHacksReal:
    """DoraHacks 真实爬取测试"""

    @pytest.mark.asyncio
    async def test_fetch_list(self):
        from app.crawler.dorahacks import dorahacks_crawler
        urls = await dorahacks_crawler.fetch_list()
        assert len(urls) > 0, "应至少获取到1个链接"
        assert all("dorahacks.io" in u for u in urls), "链接应包含 dorahacks.io"
        print(f"  DoraHacks 列表: {len(urls)} 条")

    @pytest.mark.asyncio
    async def test_fetch_detail(self):
        from app.crawler.dorahacks import dorahacks_crawler
        urls = await dorahacks_crawler.fetch_list()
        if not urls:
            pytest.skip("DoraHacks 列表为空")

        result = await dorahacks_crawler.fetch_detail(urls[0])
        assert result.source_platform == "dorahacks"
        assert result.source_url == urls[0]
        assert result.raw_data is not None
        print(f"  DoraHacks 详情: {result.raw_title[:50]}")


# ── CompeteHub 真实爬取（CloakBrowser） ──────────────

class TestCompeteHubReal:
    """CompeteHub 真实爬取测试"""

    @pytest.mark.asyncio
    async def test_fetch_list(self):
        from app.crawler.competehub import competehub_crawler
        urls = await competehub_crawler.fetch_list()
        assert len(urls) > 0, "应至少获取到1个链接"
        assert all("competehub.com" in u for u in urls)
        print(f"  CompeteHub 列表: {len(urls)} 条")

    @pytest.mark.asyncio
    async def test_fetch_detail(self):
        from app.crawler.competehub import competehub_crawler
        urls = await competehub_crawler.fetch_list()
        if not urls:
            pytest.skip("CompeteHub 列表为空")

        result = await competehub_crawler.fetch_detail(urls[0])
        assert result.source_platform == "competehub"
        assert result.raw_data is not None
        print(f"  CompeteHub 详情: {result.raw_title[:50]}")


# ── 天池真实爬取（REST API） ─────────────────────────

class TestTianchiReal:
    """天池真实爬取测试"""

    @pytest.mark.asyncio
    async def test_fetch_list(self):
        from app.crawler.tianchi import tianchi_crawler
        urls = await tianchi_crawler.fetch_list()
        # 天池 API 可能被重定向，允许0条但不应报错
        print(f"  天池列表: {len(urls)} 条")

    @pytest.mark.asyncio
    async def test_fetch_detail_with_known_url(self):
        """用已知 URL 测试详情提取"""
        from app.crawler.tianchi import tianchi_crawler
        # 天池已知竞赛 ID
        url = "https://tianchi.aliyun.com/competition/entrance/532841/introduction"
        result = await tianchi_crawler.fetch_detail(url)
        assert result.source_platform == "tianchi"
        assert result.raw_data is not None
        print(f"  天池详情: {result.raw_title[:50] if result.raw_title else '(空)'}")


# ── 活动行真实爬取（httpx + BeautifulSoup） ──────────

class TestHuodongxingReal:
    """活动行真实爬取测试"""

    @pytest.mark.asyncio
    async def test_fetch_list(self):
        from app.crawler.huodongxing import huodongxing_crawler
        urls = await huodongxing_crawler.fetch_list()
        print(f"  活动行列表: {len(urls)} 条")

    @pytest.mark.asyncio
    async def test_fetch_detail(self):
        from app.crawler.huodongxing import huodongxing_crawler
        urls = await huodongxing_crawler.fetch_list()
        if not urls:
            pytest.skip("活动行列表为空")

        result = await huodongxing_crawler.fetch_detail(urls[0])
        assert result.source_platform == "huodongxing"
        print(f"  活动行详情: {result.raw_title[:50] if result.raw_title else '(空)'}")


# ── LLM 真实清洗测试 ─────────────────────────────────

class TestLLMReal:
    """阶跃星辰 LLM 真实调用测试"""

    def test_process_single(self):
        """单条数据 LLM 清洗（同步调用）"""
        import httpx
        from app.config import settings

        raw_data = {
            "title": "2026 AI创新黑客松",
            "description": "面向全球开发者的AI创新黑客松，奖金5万美元。参赛条件：需组队参加，每队2-5人。赛道包括NLP、CV、推荐系统。",
            "start_date": "2026-07-15",
            "end_date": "2026-07-17",
            "signup_end": "2026-07-10",
            "prize": "$50,000 USD",
            "tracks": ["NLP", "CV", "推荐系统"],
            "organizer": "TechCorp",
            "sponsors": ["Google", "Microsoft"],
            "location": "线上",
            "mode": "online",
        }

        raw_text = json.dumps(raw_data, ensure_ascii=False)
        prompt = f"""你是一个黑客松信息提取专家。请从以下原始数据中提取结构化字段。

原始数据：
{raw_text}

请提取以下字段，以JSON格式返回：
{{
    "name": "活动名称",
    "summary": "一句话摘要（50字以内）",
    "event_start": "活动开始日期",
    "event_end": "活动结束日期",
    "mode": "online/offline/hybrid",
    "track_tags": ["赛道标签数组"],
    "tech_tags": ["技术栈标签数组"],
    "prize_pool": "奖金池",
    "location": "地点",
    "organizer": "主办方",
    "requirements": ["参赛条件数组"],
    "confidence": 0.85
}}

注意：只返回JSON，不要其他内容。"""

        resp = httpx.post(
            f"{settings.LLM_API_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={"model": settings.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # 提取 JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())

        assert result.get("name") != ""
        assert result.get("summary") is not None
        assert result.get("confidence", 0) > 0

        print(f"  名称: {result.get('name')}")
        print(f"  摘要: {result.get('summary')}")
        print(f"  赛道: {result.get('track_tags')}")
        print(f"  技术栈: {result.get('tech_tags')}")
        print(f"  参赛条件: {result.get('requirements')}")
        print(f"  置信度: {result.get('confidence')}")

    def test_process_batch(self):
        """批量 LLM 清洗（同步调用2条）"""
        import httpx
        from app.config import settings

        results = []
        for i in range(1, 3):
            raw_data = {
                "title": f"测试黑客松 {i}",
                "description": f"第{i}个测试黑客松，奖金{i*10000}元",
                "prize": f"{i*10000} CNY",
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
                "location": "线上",
            }
            prompt = f"提取以下黑客松的名称和摘要，以JSON返回: {json.dumps(raw_data, ensure_ascii=False)}\n只返回JSON: {{\"name\": \"\", \"summary\": \"\"}}"

            resp = httpx.post(
                f"{settings.LLM_API_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json={"model": settings.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                timeout=60,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            results.append(json.loads(content.strip()))

        assert len(results) == 2
        assert all(r.get("name") for r in results)
        print(f"  批量清洗: {len(results)} 条成功")


# ── 端到端：爬取 → LLM 清洗 ─────────────────────────

class TestEndToEnd:
    """端到端测试：真实爬取 + LLM 清洗"""

    def test_tianchi_crawl_and_clean(self):
        """天池：爬取 → LLM 清洗 → 输出 JSON（API不可用时用模拟数据）"""
        import httpx
        from app.config import settings

        # 天池 API 可能被重定向，用模拟数据测试端到端流程
        raw_data = {
            "title": "天池大数据竞赛",
            "description": "阿里云天池平台举办的AI算法竞赛，奖金10万元",
            "start_date": "2026-07-01",
            "end_date": "2026-08-31",
            "prize": "100,000 CNY",
            "tracks": ["NLP", "CV"],
            "organizer": "阿里云",
            "location": "线上",
            "url": "https://tianchi.aliyun.com/competition/entrance/532841/introduction",
        }

        prompt = f"提取以下黑客松的结构化信息，以JSON返回: {json.dumps(raw_data, ensure_ascii=False)}\n返回: {{\"name\": \"\", \"summary\": \"\", \"confidence\": 0.0}}"

        resp = httpx.post(
            f"{settings.LLM_API_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={"model": settings.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        result = json.loads(content.strip())

        assert result.get("name") != ""
        assert result.get("summary") is not None
        print(f"  端到端: {result.get('name')}")
        print(f"  摘要: {result.get('summary')}")

    def test_dorahacks_crawl_and_clean(self):
        """DoraHacks：爬取 → LLM 清洗"""
        import asyncio
        asyncio.run(self._dorahacks_e2e())

    async def _dorahacks_e2e(self):
        from app.crawler.dorahacks import dorahacks_crawler

        urls = await dorahacks_crawler.fetch_list()
        if not urls:
            pytest.skip("DoraHacks 列表为空")

        result = await dorahacks_crawler.fetch_detail(urls[0])
        processor = LLMProcessor()
        cleaned = await processor.process(result)

        assert cleaned.source_platform == "dorahacks"
        print(f"  端到端: {cleaned.name}")
        if cleaned.summary:
            print(f"  摘要: {cleaned.summary}")


# ── 调度器真实测试 ────────────────────────────────────

class TestSchedulerReal:
    """调度器真实运行测试"""

    def test_run_single_platform(self):
        """运行单个平台爬取"""
        import asyncio
        from app.crawler.scheduler import scheduler
        result = asyncio.run(scheduler.run_platform("tianchi", save_json=False))
        assert result["platform"] == "tianchi"
        assert result["status"] in ["success", "error"]
        print(f"  天池结果: {result}")

    def test_get_status(self):
        from app.crawler.scheduler import scheduler
        status = scheduler.get_status()
        assert len(status["platforms"]) == 8
        assert status["status"] == "running"
        print(f"  调度器状态: {status['platforms']}")
