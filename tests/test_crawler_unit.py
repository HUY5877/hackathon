"""爬虫离线单元测试 — 不依赖网络，覆盖核心逻辑

测试范围：
- BaseCrawler 异常分类、重试机制、UA 轮换、代理池
- LLMProcessor JSON 解析、缓存、降级策略
- Scheduler 去重逻辑、统计、历史
- 各爬虫 HTML 解析方法（用本地 HTML 片段）
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.crawler.base import (
    BaseCrawler,
    CrawlResult,
    CrawlerError,
    NetworkError,
    HTTPStatusError,
    ParseError,
    BlockedError,
    retry_async,
    _pick_user_agent,
    _USER_AGENTS,
    crawl_result_validation_error,
)
from app.crawler.extraction import (
    compact_text_fragments,
    extract_event_json_ld,
    extract_explicit_date_range,
)
from app.crawler.llm_processor import (
    LLMProcessor,
    StandardizedHackathon,
    _ResultCache,
    _extract_json_from_text,
)
from app.crawler.scheduler import (
    deduplicate,
    _normalize_name,
    _normalize_url,
    _name_similarity,
    _partition_crawl_results,
    DEDUP_SIMILARITY_THRESHOLD,
)


# ── 异常分类测试 ──────────────────────────────────────

class TestExceptions:
    def test_http_status_error_retryable(self):
        """5xx 和 429 可重试"""
        assert HTTPStatusError("err", 500).retryable is True
        assert HTTPStatusError("err", 502).retryable is True
        assert HTTPStatusError("err", 429).retryable is True

    def test_http_status_error_not_retryable(self):
        """4xx 不可重试"""
        assert HTTPStatusError("err", 404).retryable is False
        assert HTTPStatusError("err", 400).retryable is False

    def test_exception_hierarchy(self):
        """所有异常都继承自 CrawlerError"""
        assert issubclass(NetworkError, CrawlerError)
        assert issubclass(HTTPStatusError, CrawlerError)
        assert issubclass(ParseError, CrawlerError)
        assert issubclass(BlockedError, CrawlerError)


class TestEvidenceBasedExtraction:
    def test_explicit_date_range_requires_connector(self):
        assert extract_explicit_date_range(
            "Event dates: 2026-07-15 to 2026-07-17"
        ) == ("2026-07-15", "2026-07-17")
        assert extract_explicit_date_range(
            "Published 2026-01-01; registration 2026-02-01"
        ) == (None, None)

    def test_explicit_date_range_rejects_three_dates(self):
        assert extract_explicit_date_range(
            "2026-01-01 to 2026-01-02, updated 2026-01-03"
        ) == (None, None)
        assert extract_explicit_date_range(
            "Jan 1-2, 2026, updated Jan 3, 2026"
        ) == (None, None)

    def test_json_ld_event_supports_graph_nesting(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            """
            <script type="application/ld+json">
            {"@graph":[{"@type":"WebPage"},{"@type":"Event","name":"Official Event",
            "startDate":"2026-09-01","endDate":"2026-09-02",
            "eventAttendanceMode":"https://schema.org/OnlineEventAttendanceMode"}]}
            </script>
            """,
            "lxml",
        )

        data = extract_event_json_ld(soup)

        assert data["title"] == "Official Event"
        assert data["start_date"] == "2026-09-01"
        assert data["end_date"] == "2026-09-02"
        assert data["mode"] == "online"

    def test_selected_fragments_do_not_fall_back_to_navigation_text(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(
            '<nav>Online events</nav><div class="event-mode">In-person only</div>',
            "lxml",
        )

        assert compact_text_fragments(
            soup, selectors=(".event-mode",), max_length=100
        ) == ["In-person only"]

    def test_crawl_result_validation_rejects_failed_and_incomplete_rows(self):
        failed = CrawlResult("p", "https://example.com/1", "Event", success=False)
        missing_title = CrawlResult("p", "https://example.com/2", "")
        invalid_url = CrawlResult("p", "not-a-url", "Event")
        valid = CrawlResult("p", "https://example.com/3", "Event")

        assert crawl_result_validation_error(failed) is not None
        assert crawl_result_validation_error(missing_title) == "missing_required_title"
        assert crawl_result_validation_error(invalid_url) == "invalid_source_url"
        assert crawl_result_validation_error(valid) is None


# ── 重试机制测试 ──────────────────────────────────────

class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """首次成功不重试"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_success_on_second_attempt(self):
        """首次失败，第二次成功"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise NetworkError("first fail")
            return "ok"

        result = await retry_async(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """重试耗尽后抛出异常"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise NetworkError("always fail")

        with pytest.raises(NetworkError):
            await retry_async(func, max_retries=2, base_delay=0.01)
        assert call_count == 3  # 1 + 2 retries

    @pytest.mark.asyncio
    async def test_retry_non_retryable_not_retried(self):
        """不可重试异常不重试"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await retry_async(func, max_retries=3, base_delay=0.01)
        assert call_count == 1


# ── UA 轮换测试 ───────────────────────────────────────

class TestUserAgentRotation:
    def test_pick_user_agent_returns_from_pool(self):
        ua = _pick_user_agent()
        assert ua in _USER_AGENTS

    def test_pick_user_agent_returns_string(self):
        ua = _pick_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 0


# ── BaseCrawler 配置测试 ─────────────────────────────

class TestBaseCrawlerConfig:
    def test_default_config_from_settings(self):
        """默认从 settings 读取配置"""
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = "https://example.com"

            async def fetch_list(self):
                return []

            async def fetch_detail(self, url):
                return CrawlResult(
                    source_platform="dummy",
                    source_url=url,
                    raw_title="",
                )

        c = DummyCrawler()
        assert c.timeout > 0
        assert c.max_retries >= 0
        assert c.request_delay >= 0

    def test_proxy_pool_parsing(self):
        """代理池逗号分隔解析"""
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return []

            async def fetch_detail(self, url):
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="")

        c = DummyCrawler(proxy="http://p1:8080,http://p2:8080,http://p3:8080")
        assert len(c._proxy_pool) == 3
        # 轮询
        p1 = c._current_proxy()
        p2 = c._current_proxy()
        p3 = c._current_proxy()
        p4 = c._current_proxy()
        assert p1 != p2 != p3
        assert p4 == p1  # 循环

    def test_safe_parse_json_valid(self):
        assert BaseCrawler._safe_parse_json('{"a": 1}') == {"a": 1}

    def test_safe_parse_json_invalid(self):
        with pytest.raises(ParseError):
            BaseCrawler._safe_parse_json("not json")


# ── BaseCrawler.run 限流测试 ─────────────────────────

class TestBaseCrawlerRun:
    @pytest.mark.asyncio
    async def test_run_max_items_limit(self):
        """max_items 限制抓取数量"""
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return [f"https://example.com/{i}" for i in range(10)]

            async def fetch_detail(self, url):
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="t")

        c = DummyCrawler(request_delay=0)
        results = await c.run(max_items=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_run_handles_blocked_error(self):
        """BlockedError 中断抓取"""
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return ["https://example.com/1", "https://example.com/2"]

            async def fetch_detail(self, url):
                raise BlockedError("blocked")

        c = DummyCrawler(request_delay=0)
        results = await c.run()
        assert len(results) == 0  # 第一条就 BlockedError，中断

    @pytest.mark.asyncio
    async def test_run_records_failed_results(self):
        """CrawlerError 记录为失败结果"""
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return ["https://example.com/1", "https://example.com/2"]

            async def fetch_detail(self, url):
                if "1" in url:
                    raise HTTPStatusError("fail", 500)
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="ok")

        c = DummyCrawler(request_delay=0)
        results = await c.run()
        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True


# ── LLM JSON 解析测试 ─────────────────────────────────

class TestLLMJsonParsing:
    def test_pure_json(self):
        result = _extract_json_from_text('{"name": "test", "confidence": 0.9}')
        assert result == {"name": "test", "confidence": 0.9}

    def test_json_code_block(self):
        text = '```json\n{"name": "test"}\n```'
        result = _extract_json_from_text(text)
        assert result == {"name": "test"}

    def test_plain_code_block(self):
        text = '```\n{"name": "test"}\n```'
        result = _extract_json_from_text(text)
        assert result == {"name": "test"}

    def test_json_embedded_in_text(self):
        text = 'Here is the result: {"name": "test", "value": 42} and more text'
        result = _extract_json_from_text(text)
        assert result == {"name": "test", "value": 42}

    def test_nested_json(self):
        text = 'prefix {"a": {"b": [1, 2, 3]}, "c": true} suffix'
        result = _extract_json_from_text(text)
        assert result == {"a": {"b": [1, 2, 3]}, "c": True}

    def test_json_with_braces_in_string(self):
        text = '{"msg": "contains } brace", "n": 1}'
        result = _extract_json_from_text(text)
        assert result == {"msg": "contains } brace", "n": 1}

    def test_empty_content(self):
        assert _extract_json_from_text("") is None
        assert _extract_json_from_text(None) is None

    def test_no_json(self):
        assert _extract_json_from_text("just plain text") is None

    def test_json_with_escaped_quotes(self):
        text = '{"msg": "say \\"hello\\""}'
        result = _extract_json_from_text(text)
        assert result == {"msg": 'say "hello"'}


# ── LLM 缓存测试 ──────────────────────────────────────

class TestLLMCache:
    def test_cache_set_get(self):
        cache = _ResultCache(ttl=60)
        cache.set("key1", {"name": "test"})
        assert cache.get("key1") == {"name": "test"}

    def test_cache_miss(self):
        cache = _ResultCache(ttl=60)
        assert cache.get("nonexistent") is None

    def test_cache_clear(self):
        cache = _ResultCache(ttl=60)
        cache.set("key1", {"a": 1})
        cache.clear()
        assert cache.get("key1") is None
        assert len(cache) == 0

    def test_cache_ttl_expiry(self):
        """TTL 过期后返回 None"""
        import time
        cache = _ResultCache(ttl=0)  # 立即过期
        cache.set("key1", {"a": 1})
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_cache_len(self):
        cache = _ResultCache(ttl=60)
        cache.set("k1", {"a": 1})
        cache.set("k2", {"b": 2})
        assert len(cache) == 2


# ── LLM Processor 降级测试 ────────────────────────────

class TestLLMProcessorFallback:
    @pytest.mark.asyncio
    async def test_process_without_api_key(self):
        """无 API Key 时返回基础结果"""
        with patch("app.crawler.llm_processor.settings") as mock_settings:
            mock_settings.LLM_API_KEY = ""
            mock_settings.LLM_API_BASE_URL = "http://localhost"
            mock_settings.LLM_MODEL = "test"
            mock_settings.CRAWLER_LLM_CACHE_TTL = 60

            proc = LLMProcessor()
            result = await proc.process(CrawlResult(
                source_platform="test",
                source_url="http://example.com",
                raw_title="Test Hackathon",
                raw_data={"title": "Test Hackathon", "prize": "$1000"},
            ))

        assert result.name == "Test Hackathon"
        assert result.prize_pool == "$1000"
        assert result.llm_confidence == 0.0  # 未调用 LLM

    @pytest.mark.asyncio
    async def test_process_with_llm_failure(self):
        """LLM 调用失败时降级返回基础结果"""
        with patch("app.crawler.llm_processor.settings") as mock_settings:
            mock_settings.LLM_API_KEY = "fake-key"
            mock_settings.LLM_API_BASE_URL = "http://localhost"
            mock_settings.LLM_MODEL = "test"
            mock_settings.CRAWLER_LLM_CACHE_TTL = 60

            proc = LLMProcessor()
            # mock _call_llm 抛异常
            proc._call_llm = AsyncMock(side_effect=Exception("LLM down"))

            result = await proc.process(CrawlResult(
                source_platform="test",
                source_url="http://example.com",
                raw_title="Test",
                raw_data={"title": "Test"},
            ))

        assert result.name == "Test"
        assert result.llm_confidence == 0.0

    def test_make_slug(self):
        assert LLMProcessor._make_slug("Hello World") == "hello-world"
        assert LLMProcessor._make_slug("AI/Hackathon 2026") == "ai-hackathon-2026"
        assert LLMProcessor._make_slug("中文活动") == "中文活动"
        assert LLMProcessor._make_slug("") == "untitled"

    def test_merge_llm_result(self):
        proc = LLMProcessor.__new__(LLMProcessor)
        base = StandardizedHackathon(
            name="Original",
            slug="original",
            track_tags=["AI"],
            sponsors=["Google"],
        )
        llm_result = {
            "name": "Updated Name",
            "summary": "A summary",
            "track_tags": ["AI", "Web"],
            "tech_tags": ["Python"],
            "sponsors": ["Google", "Microsoft"],
            "confidence": 0.9,
        }
        proc._merge_llm_result(base, llm_result, "Original")
        assert base.name == "Updated Name"
        assert base.summary == "A summary"
        assert "Web" in base.track_tags
        assert "AI" in base.track_tags
        assert base.tech_tags == ["Python"]
        assert "Microsoft" in base.sponsors
        assert base.llm_confidence == 0.9


# ── 去重逻辑测试 ──────────────────────────────────────

class TestDeduplication:
    def test_normalize_name(self):
        assert _normalize_name("AI Hackathon 2026") == "ai2026"
        assert _normalize_name("Hello World!") == "helloworld"
        assert _normalize_name("黑客松") == ""
        assert _normalize_name("") == ""

    def test_normalize_url(self):
        assert _normalize_url("https://example.com/path/") == "https://example.com/path"
        assert _normalize_url("https://example.com/path?q=1#frag") == "https://example.com/path"
        assert _normalize_url("HTTPS://Example.COM/Path") == "https://example.com/path"
        assert _normalize_url("") == ""

    def test_name_similarity_identical(self):
        assert _name_similarity("AI Hackathon", "AI Hackathon") == 1.0

    def test_name_similarity_different(self):
        assert _name_similarity("AI Hackathon", "Web Conference") < 0.5

    def test_name_similarity_keeps_edition_year(self):
        """不同届赛事不能因为移除年份而变成同一名称。"""
        sim = _name_similarity("AI Hackathon 2026", "AI Hackathon 2025")
        assert sim < DEDUP_SIMILARITY_THRESHOLD

    def test_dedup_url_match(self):
        """URL 相同去重"""
        items = [
            StandardizedHackathon(name="A", slug="a", source_url="https://example.com/1", source_platform="p1"),
            StandardizedHackathon(name="B", slug="b", source_url="https://example.com/1/", source_platform="p2"),
        ]
        deduped, merged = deduplicate(items)
        assert len(deduped) == 1
        assert len(merged) == 1
        assert merged[0]["reason"] == "url_match"

    def test_dedup_name_similarity(self):
        """名称与赛事日期同时一致才允许跨来源去重。"""
        items = [
            StandardizedHackathon(
                name="AI Hackathon 2026",
                slug="ai",
                source_url="https://p1.com/1",
                source_platform="p1",
                event_start="2026-08-01",
            ),
            StandardizedHackathon(
                name="AI Hackathon 2026!",
                slug="ai2",
                source_url="https://p2.com/2",
                source_platform="p2",
                event_start="2026-08-01",
            ),
        ]
        deduped, merged = deduplicate(items)
        assert len(deduped) == 1
        assert merged[0]["reason"] == "name_and_date_match"

    def test_dedup_does_not_merge_different_editions(self):
        items = [
            StandardizedHackathon(
                name="AI Hackathon 2025", slug="a", source_url="https://p1.com/1",
                source_platform="p1", event_start="2025-08-01",
            ),
            StandardizedHackathon(
                name="AI Hackathon 2026", slug="b", source_url="https://p2.com/2",
                source_platform="p2", event_start="2026-08-01",
            ),
        ]

        deduped, merged = deduplicate(items)

        assert len(deduped) == 2
        assert merged == []

    def test_dedup_does_not_merge_names_without_date_evidence(self):
        items = [
            StandardizedHackathon(name="AI Hackathon", slug="a", source_url="https://p1.com/1", source_platform="p1"),
            StandardizedHackathon(name="AI Hackathon", slug="b", source_url="https://p2.com/2", source_platform="p2"),
        ]

        deduped, merged = deduplicate(items)

        assert len(deduped) == 2
        assert merged == []

    def test_dedup_no_false_positive(self):
        """不同活动不去重"""
        items = [
            StandardizedHackathon(name="AI Hackathon", slug="ai", source_url="https://p1.com/1", source_platform="p1"),
            StandardizedHackathon(name="Web Conference", slug="web", source_url="https://p2.com/2", source_platform="p2"),
        ]
        deduped, merged = deduplicate(items)
        assert len(deduped) == 2
        assert len(merged) == 0

    def test_dedup_merges_fields(self):
        """去重时合并字段"""
        items = [
            StandardizedHackathon(
                name="AI Hackathon", slug="ai",
                source_url="https://p1.com/1", source_platform="p1",
                track_tags=["AI"], summary="Original summary",
            ),
            StandardizedHackathon(
                name="AI Hackathon", slug="ai",
                source_url="https://p1.com/1", source_platform="p2",
                track_tags=["Web"], tech_tags=["Python"],
                location="Online", llm_confidence=0.95,
            ),
        ]
        deduped, _ = deduplicate(items)
        assert len(deduped) == 1
        merged = deduped[0]
        assert "Web" in merged.track_tags
        assert "AI" in merged.track_tags
        assert merged.tech_tags == ["Python"]
        assert merged.location == "Online"
        assert merged.llm_confidence == 0.95

    def test_dedup_empty_list(self):
        deduped, merged = deduplicate([])
        assert deduped == []
        assert merged == []


# ── 爬虫 HTML 解析测试 ────────────────────────────────

class TestDevpostParsing:
    def test_parse_detail_html(self):
        from app.crawler.devpost import DevpostCrawler
        html = """
        <html><body>
            <h1>AI Challenge 2026</h1>
            <div class="hackathon-description">A great AI hackathon</div>
            <div class="prize">$10,000</div>
            <span class="location">San Francisco</span>
            <div class="tag">AI</div>
            <div class="tag">ML</div>
        </body></html>
        """
        crawler = DevpostCrawler()
        data = crawler._parse_detail_html(html, "https://devpost.com/hackathons/ai-challenge-2026")
        assert data["title"] == "AI Challenge 2026"
        assert "great AI hackathon" in data["description"]
        assert data["prize"] == "$10,000"
        assert data["location"] == "San Francisco"
        assert "AI" in data["tracks"]
        assert "ML" in data["tracks"]


class TestSaikrParsing:
    def test_dates_are_assigned_by_business_label(self):
        from app.crawler.saikr import SaikrCrawler

        html = """
        <html><body>
            <h1>全国 AI 挑战赛</h1>
            <div class="info-item">发布日期：2025-12-20</div>
            <div class="info-item">报名时间：2026-01-01 至 2026-02-01</div>
            <div class="info-item">比赛时间：2026-03-10 至 2026-03-12</div>
        </body></html>
        """

        data = SaikrCrawler()._parse_detail_html(html, "https://www.saikr.com/vse/test")

        assert data["signup_start"] == "2026-01-01"
        assert data["signup_end"] == "2026-02-01"
        assert data["start_date"] == "2026-03-10"
        assert data["end_date"] == "2026-03-12"

    def test_unlabeled_page_dates_are_not_treated_as_event_schedule(self):
        from app.crawler.saikr import SaikrCrawler

        html = """
        <html><body>
            <h1>全国 AI 挑战赛</h1>
            <p>文章发布于 2025-12-20，更新于 2025-12-21。</p>
        </body></html>
        """

        data = SaikrCrawler()._parse_detail_html(html, "https://www.saikr.com/vse/test")

        assert "start_date" not in data
        assert "end_date" not in data


class TestMLHParsing:
    def test_parse_list_html(self):
        from app.crawler.mlh import MLHCrawler
        html = """
        <div>
            <a href="/events/spring-hack-2026">Spring Hack</a>
            <a href="https://mlh.io/events/summer-hack">Summer Hack</a>
            <a href="/seasons/2026/events">Season Page</a>
        </div>
        """
        crawler = MLHCrawler()
        urls = crawler._parse_list_html(html)
        assert len(urls) == 2
        assert "https://mlh.io/events/spring-hack-2026" in urls
        assert "https://mlh.io/events/summer-hack" in urls

    def test_embedded_auxiliary_urls_are_canonicalized(self):
        from app.crawler.mlh import MLHCrawler

        html = """
        <script type="application/json">
        {"events":[{"slug":"spring-hack","url":"/events/spring-hack/prizes"},
        {"slug":"spring-hack","url":"/events/spring-hack/schedule"}]}
        </script>
        """

        assert MLHCrawler()._parse_list_html(html) == [
            "https://mlh.io/events/spring-hack"
        ]

    def test_parse_date_range_iso(self):
        from app.crawler.mlh import MLHCrawler
        data = {}
        MLHCrawler._parse_date_range("2026-01-15 to 2026-01-17", data)
        assert data["start_date"] == "2026-01-15"
        assert data["end_date"] == "2026-01-17"

    def test_parse_date_range_month_name(self):
        from app.crawler.mlh import MLHCrawler
        data = {}
        MLHCrawler._parse_date_range("Jan 15-17, 2026", data)
        assert data["start_date"] == "2026-01-15"
        assert data["end_date"] == "2026-01-17"

    def test_parse_date_range_single_iso(self):
        from app.crawler.mlh import MLHCrawler
        data = {}
        MLHCrawler._parse_date_range("2026-01-15", data)
        assert data["start_date"] == "2026-01-15"
        assert "end_date" not in data


class TestHuodongxingParsing:
    def test_parse_list_html(self):
        from app.crawler.huodongxing import HuodongxingCrawler
        html = """
        <div>
            <a href="/event/12345.html">活动1</a>
            <a href="/event/67890">活动2</a>
            <a href="/events/list">列表</a>
        </div>
        """
        crawler = HuodongxingCrawler()
        urls = crawler._parse_list_html(html)
        assert len(urls) == 2
        assert "https://www.huodongxing.com/event/12345.html" in urls

    def test_parse_detail_html(self):
        from app.crawler.huodongxing import HuodongxingCrawler
        html = """
        <html><body>
            <h1>2026 AI 黑客松</h1>
            <div class="event-detail">
                <div class="info-item">时间：2026-07-15 09:00</div>
                <div class="info-item">地点：线上</div>
                <div class="info-item">主办方：TechCorp</div>
            </div>
            <span class="tag">AI</span>
        </body></html>
        """
        crawler = HuodongxingCrawler()
        data = crawler._parse_detail_html(html, "https://www.huodongxing.com/event/12345")
        assert data["title"] == "2026 AI 黑客松"
        assert "2026-07-15" in data.get("start_date", "")
        assert data["location"] == "线上"
        assert data["organizer"] == "TechCorp"
        assert data["mode"] == "online"
        assert "AI" in data.get("tracks", [])

    def test_labeled_time_range_sets_both_event_dates(self):
        from app.crawler.huodongxing import HuodongxingCrawler

        html = """
        <html><body>
            <h1>AI 黑客松</h1>
            <div class="info-item">时间：2026-07-15 09:00 至 2026-07-17 18:00</div>
            <time datetime="2025-12-01">发布时间</time>
        </body></html>
        """

        data = HuodongxingCrawler()._parse_detail_html(
            html, "https://www.huodongxing.com/event/12345"
        )

        assert data["start_date"].startswith("2026-07-15")
        assert data["end_date"].startswith("2026-07-17")


class TestTianchiParsing:
    def test_extract_items_data_list(self):
        from app.crawler.tianchi import TianchiCrawler
        crawler = TianchiCrawler()
        data = {"data": {"list": [{"id": 1}, {"id": 2}]}}
        items = crawler._extract_items(data)
        assert len(items) == 2

    def test_extract_items_nested(self):
        from app.crawler.tianchi import TianchiCrawler
        crawler = TianchiCrawler()
        data = {"data": {"data": {"list": [{"id": 1}]}}}
        items = crawler._extract_items(data)
        assert len(items) == 1

    def test_extract_items_empty(self):
        from app.crawler.tianchi import TianchiCrawler
        crawler = TianchiCrawler()
        assert crawler._extract_items({}) == []
        assert crawler._extract_items({"data": {}}) == []
        assert crawler._extract_items("not dict") == []

    def test_empty_detail_is_explicit_failure(self):
        from app.crawler.tianchi import TianchiCrawler

        result = TianchiCrawler()._build_result(
            "https://tianchi.aliyun.com/competition/entrance/1/introduction",
            {"title": "", "error": "detail unavailable"},
        )

        assert result.success is False
        assert result.error_message == "detail unavailable"


# ── Scheduler 测试 ────────────────────────────────────

class TestScheduler:
    def test_scheduler_init(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        assert s._stats["total_runs"] == 0
        assert s._max_history == 50

    def test_partition_rejects_failed_and_missing_title_results(self):
        results = [
            CrawlResult("p", "https://example.com/ok", "Valid Event"),
            CrawlResult("p", "https://example.com/fail", "", success=False, error_message="blocked"),
            CrawlResult("p", "https://example.com/empty", ""),
        ]

        usable, rejected = _partition_crawl_results(results)

        assert [item.raw_title for item in usable] == ["Valid Event"]
        assert {item["reason"] for item in rejected} == {"blocked", "missing_required_title"}

    def test_record_run_success(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        s._record_run({
            "status": "success",
            "raw_count": 10,
            "cleaned_count": 8,
        })
        assert s._stats["total_runs"] == 1
        assert s._stats["success_runs"] == 1
        assert s._stats["total_raw"] == 10
        assert s._stats["total_cleaned"] == 8

    def test_record_run_error(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        s._record_run({"status": "error"})
        assert s._stats["total_runs"] == 1
        assert s._stats["error_runs"] == 1
        assert s._stats["success_runs"] == 0

    def test_history_limit(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        s._max_history = 3
        for i in range(5):
            s._record_run({"platform": f"p{i}", "status": "success"})
        assert len(s._history) == 3
        assert s._history[0]["platform"] == "p2"  # 最早的被移除

    def test_get_history(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        for i in range(10):
            s._record_run({"platform": f"p{i}", "status": "success"})
        history = s.get_history(limit=5)
        assert len(history) == 5

    def test_build_summary(self):
        from app.crawler.scheduler import CrawlerScheduler
        s = CrawlerScheduler()
        results = [
            {"status": "success", "raw_count": 10, "cleaned_count": 8},
            {"status": "success", "raw_count": 5, "cleaned_count": 4},
            {"status": "error"},
        ]
        summary = s._build_summary(results)
        assert summary["total_platforms"] == 3
        assert summary["success_platforms"] == 2
        assert summary["error_platforms"] == 1
        assert summary["total_raw"] == 15
        assert summary["total_cleaned"] == 12


# ── 重试机制：retryable 属性测试 ──────────────────────

class TestRetryableAttribute:
    """测试 retry_async 对 HTTPStatusError.retryable 属性的处理"""

    @pytest.mark.asyncio
    async def test_4xx_not_retried(self):
        """4xx 错误（非 429）不应重试"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise HTTPStatusError("not found", 404)

        with pytest.raises(HTTPStatusError):
            await retry_async(
                func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(NetworkError, HTTPStatusError),
            )
        assert call_count == 1  # 不重试

    @pytest.mark.asyncio
    async def test_5xx_retried(self):
        """5xx 错误应重试"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise HTTPStatusError("server error", 500)

        with pytest.raises(HTTPStatusError):
            await retry_async(
                func,
                max_retries=2,
                base_delay=0.01,
                retryable_exceptions=(NetworkError, HTTPStatusError),
            )
        assert call_count == 3  # 1 + 2 次重试

    @pytest.mark.asyncio
    async def test_429_retried(self):
        """429 频控应重试"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise HTTPStatusError("rate limited", 429)
            return "ok"

        result = await retry_async(
            func,
            max_retries=3,
            base_delay=0.01,
            retryable_exceptions=(NetworkError, HTTPStatusError),
        )
        assert result == "ok"
        assert call_count == 3


# ── Mapper 测试 ──────────────────────────────────────

class TestMapper:
    def test_parse_date_iso(self):
        from app.crawler.mapper import parse_date
        d = parse_date("2026-07-15")
        assert d is not None
        assert d.year == 2026
        assert d.month == 7
        assert d.day == 15

    def test_parse_date_chinese(self):
        from app.crawler.mapper import parse_date
        d = parse_date("2026年7月15日")
        assert d is not None
        assert d.year == 2026

    def test_parse_date_iso_with_time(self):
        from app.crawler.mapper import parse_date
        d = parse_date("2026-07-15T09:00:00")
        assert d is not None
        assert d.hour == 9

    def test_parse_date_invalid(self):
        from app.crawler.mapper import parse_date
        assert parse_date("") is None
        assert parse_date(None) is None
        assert parse_date("not a date") is None

    def test_parse_date_extract_from_text(self):
        from app.crawler.mapper import parse_date
        d = parse_date("活动时间：2026/07/15 上午")
        assert d is not None
        assert d.year == 2026

    def test_parse_date_rejects_ambiguous_mixed_text(self):
        from app.crawler.mapper import parse_date

        assert parse_date("发布 2026-01-01，活动 2026-07-15") is None

    def test_normalize_mode(self):
        from app.crawler.mapper import normalize_mode
        from app.models.hackathon import HackathonMode
        assert normalize_mode("online") == HackathonMode.ONLINE
        assert normalize_mode("offline") == HackathonMode.OFFLINE
        assert normalize_mode("in-person") == HackathonMode.OFFLINE
        assert normalize_mode("hybrid") == HackathonMode.HYBRID
        assert normalize_mode(None) == HackathonMode.ONLINE
        assert normalize_mode("unknown") == HackathonMode.ONLINE

    def test_normalize_status(self):
        from app.crawler.mapper import normalize_status
        from app.models.hackathon import HackathonStatus
        assert normalize_status("upcoming") == HackathonStatus.UPCOMING
        assert normalize_status("registering") == HackathonStatus.REGISTERING
        assert normalize_status("open") == HackathonStatus.REGISTERING
        assert normalize_status("ongoing") == HackathonStatus.ONGOING
        assert normalize_status("ended") == HackathonStatus.ENDED

    def test_compute_status_from_dates(self):
        from app.crawler.mapper import compute_status_from_dates
        from app.models.hackathon import HackathonStatus
        from datetime import datetime, timedelta

        now = datetime(2026, 6, 15)

        # 活动已结束
        past_end = now - timedelta(days=10)
        assert compute_status_from_dates(None, None, past_end, now) == HackathonStatus.ENDED

        # 活动进行中
        past_start = now - timedelta(days=1)
        future_end = now + timedelta(days=1)
        assert compute_status_from_dates(None, past_start, future_end, now) == HackathonStatus.ONGOING

        # 报名中
        future_reg_end = now + timedelta(days=5)
        future_start = now + timedelta(days=10)
        assert compute_status_from_dates(future_reg_end, future_start, None, now) == HackathonStatus.REGISTERING

    def test_ensure_unique_slug(self):
        from app.crawler.mapper import ensure_unique_slug
        existing = {"foo", "bar", "foo-2"}
        assert ensure_unique_slug("baz", existing) == "baz"
        assert ensure_unique_slug("foo", existing) == "foo-3"
        assert ensure_unique_slug("bar", existing) == "bar-2"

    def test_to_hackathon_orm_basic(self):
        from app.crawler.mapper import to_hackathon_orm
        from app.models.hackathon import Hackathon, HackathonStatus, HackathonMode

        item = StandardizedHackathon(
            name="Test Hackathon",
            slug="test-hackathon",
            description="A test event",
            summary="Test summary",
            event_start="2026-07-15",
            event_end="2026-07-17",
            mode="online",
            prize_pool="$10,000",
            prize_pool_usd=10000.0,
            source_url="https://example.com/hackathon",
            source_platform="devpost",
            llm_confidence=0.9,
        )
        orm = to_hackathon_orm(item)
        assert isinstance(orm, Hackathon)
        assert orm.name == "Test Hackathon"
        assert orm.slug == "test-hackathon"
        assert orm.event_start.year == 2026
        assert orm.mode == HackathonMode.ONLINE
        assert orm.prize_pool_usd == 10000.0
        assert orm.source_platform == "devpost"
        assert orm.llm_confidence == 0.9

    def test_to_hackathon_orm_rejects_inverted_date_ranges(self):
        from app.crawler.mapper import to_hackathon_orm

        item = StandardizedHackathon(
            name="Inverted Dates",
            slug="inverted-dates",
            registration_start="2026-07-20",
            registration_end="2026-07-01",
            event_start="2026-08-05",
            event_end="2026-08-01",
            source_url="https://example.com/inverted",
            source_platform="test",
        )

        orm = to_hackathon_orm(item)

        assert orm.registration_start is None
        assert orm.registration_end is None
        assert orm.event_start is None
        assert orm.event_end is None

    def test_to_hackathon_orm_batch_slug_dedup(self):
        from app.crawler.mapper import to_hackathon_orm_batch

        items = [
            StandardizedHackathon(name="A", slug="dup", source_url="u1"),
            StandardizedHackathon(name="B", slug="dup", source_url="u2"),
            StandardizedHackathon(name="C", slug="dup", source_url="u3"),
        ]
        orms = to_hackathon_orm_batch(items)
        slugs = [o.slug for o in orms]
        assert len(set(slugs)) == 3  # 全部唯一
        assert "dup" in slugs
        assert "dup-2" in slugs
        assert "dup-3" in slugs


# ── Persistence 测试（使用 Mock）──────────────

class TestPersistence:
    @pytest.mark.asyncio
    async def test_persist_batch_insert_with_mock(self):
        """测试批量插入新数据（使用 Mock session）"""
        from app.crawler.persistence import persist_batch
        from unittest.mock import AsyncMock, MagicMock
        from sqlalchemy import select

        items = [
            StandardizedHackathon(
                name="Hack A",
                slug="hack-a",
                source_url="https://example.com/a",
                source_platform="devpost",
            ),
            StandardizedHackathon(
                name="Hack B",
                slug="hack-b",
                source_url="https://example.com/b",
                source_platform="mlh",
            ),
        ]

        # Mock session
        session = AsyncMock()
        session.add = MagicMock()
        # _fetch_existing_by_source_url 返回空
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)
        # _fetch_existing_slugs 返回空 set
        slugs_mock = MagicMock()
        slugs_mock.all.return_value = []
        # 第二次 execute 调用返回 slugs
        session.execute = AsyncMock(side_effect=[result_mock, slugs_mock])
        session.commit = AsyncMock()

        result = await persist_batch(session, items)

        assert result.total == 2
        assert result.inserted == 2
        assert result.updated == 0
        assert len(result.errors) == 0
        # 应该 add 了 2 个对象
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_persist_batch_skip_empty_name_with_mock(self):
        """测试跳过无名称数据"""
        from app.crawler.persistence import persist_batch
        from unittest.mock import AsyncMock, MagicMock

        items = [
            StandardizedHackathon(name="", slug="empty", source_url="u1"),
            StandardizedHackathon(name="Valid", slug="valid", source_url="u2"),
        ]

        session = AsyncMock()
        session.add = MagicMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        slugs_mock = MagicMock()
        slugs_mock.all.return_value = []
        session.execute = AsyncMock(side_effect=[result_mock, slugs_mock])
        session.commit = AsyncMock()

        result = await persist_batch(session, items)

        assert result.skipped == 1
        assert result.inserted == 1

    @pytest.mark.asyncio
    async def test_persist_batch_empty_list(self):
        """测试空列表"""
        from app.crawler.persistence import persist_batch
        from unittest.mock import AsyncMock

        session = AsyncMock()
        result = await persist_batch(session, [])

        assert result.total == 0
        assert result.inserted == 0
        assert result.updated == 0
        assert result.skipped == 0

    @pytest.mark.asyncio
    async def test_persistence_result_to_dict(self):
        """测试 PersistenceResult 序列化"""
        from app.crawler.persistence import PersistenceResult
        r = PersistenceResult()
        r.inserted = 5
        r.updated = 3
        r.skipped = 2
        r.errors.append("some error")
        d = r.to_dict()
        assert d["inserted"] == 5
        assert d["updated"] == 3
        assert d["skipped"] == 2
        assert len(d["errors"]) == 1

    def test_persistence_result_repr(self):
        """测试 PersistenceResult repr"""
        from app.crawler.persistence import PersistenceResult
        r = PersistenceResult()
        r.inserted = 1
        r.updated = 2
        r.skipped = 3
        s = repr(r)
        assert "inserted=1" in s
        assert "updated=2" in s
        assert "skipped=3" in s


# ── LLM 熔断器测试 ──────────────────────────────────

class TestLLMCircuitBreaker:
    def test_circuit_opens_after_consecutive_failures(self):
        """连续失败达到阈值后熔断器开启"""
        proc = LLMProcessor()
        proc._consecutive_failures = 0
        proc._circuit_open = False

        for i in range(proc.MAX_CONSECUTIVE_FAILURES):
            proc._consecutive_failures += 1
            proc._check_circuit()

        assert proc._circuit_open is True

    def test_circuit_resets_on_success(self):
        """成功后重置连续失败计数"""
        proc = LLMProcessor()
        proc._consecutive_failures = 3
        proc._circuit_open = False

        # 模拟成功
        proc._consecutive_failures = 0
        proc._check_circuit()

        assert proc._circuit_open is False
        assert proc._consecutive_failures == 0

    def test_reset_circuit(self):
        """手动重置熔断器"""
        proc = LLMProcessor()
        proc._circuit_open = True
        proc._consecutive_failures = 10

        proc.reset_circuit()

        assert proc._circuit_open is False
        assert proc._consecutive_failures == 0

    def test_get_stats(self):
        """获取统计信息"""
        proc = LLMProcessor()
        proc._total_calls = 10
        proc._total_cache_hits = 5
        proc._total_failures = 2

        stats = proc.get_stats()
        assert stats["total_calls"] == 10
        assert stats["cache_hits"] == 5
        assert stats["total_failures"] == 2
        assert "circuit_open" in stats
        assert "cache_size" in stats


# ── CloakBrowser 基类测试 ────────────────────────────

class TestCloakBrowserBase:
    @pytest.mark.asyncio
    async def test_cloak_not_available_fallback(self):
        """CloakBrowser 不可用时应返回 None"""
        from app.crawler.cloak_base import CloakBrowserBaseCrawler

        class TestCrawler(CloakBrowserBaseCrawler):
            platform_name = "test"

        crawler = TestCrawler()
        # 模拟 cloakbrowser 未安装
        crawler._cloak_available = False
        browser = await crawler._get_browser()
        assert browser is None

    @pytest.mark.asyncio
    async def test_close_is_async(self):
        """close 方法应为 async（与基类一致）"""
        from app.crawler.cloak_base import CloakBrowserBaseCrawler
        import inspect

        class TestCrawler(CloakBrowserBaseCrawler):
            platform_name = "test"

        crawler = TestCrawler()
        assert inspect.iscoroutinefunction(crawler.close)
        # 应该能 await 调用而不报错
        await crawler.close()


# ── ETHGlobal 爬虫测试 ──────────────────────────────

class TestETHGlobalCrawler:
    def test_parse_list_html(self):
        """测试解析 ETHGlobal 列表页 HTML"""
        from app.crawler.ethglobal import ETHGlobalCrawler
        html = """
        <html><body>
            <a href="/events/lisbon2026">ETHGlobal Lisbon 2026</a>
            <a href="/events/tokyo2026">ETHGlobal Tokyo 2026</a>
            <a href="/events/ethonline2026">ETHOnline 2026</a>
            <a href="/events">All Events</a>
            <a href="/events/pragma-lisbon2026">Pragma Lisbon</a>
        </body></html>
        """
        crawler = ETHGlobalCrawler()
        urls = crawler._parse_list_html(html)
        assert len(urls) == 4  # 排除 /events 本身
        assert "https://ethglobal.com/events/lisbon2026" in urls
        assert "https://ethglobal.com/events/tokyo2026" in urls
        assert "https://ethglobal.com/events/ethonline2026" in urls
        assert "https://ethglobal.com/events/pragma-lisbon2026" in urls

    def test_parse_list_html_empty(self):
        """测试空列表"""
        from app.crawler.ethglobal import ETHGlobalCrawler
        crawler = ETHGlobalCrawler()
        assert crawler._parse_list_html("<html></html>") == []

    def test_parse_detail_html_basic(self):
        """测试解析详情页"""
        from app.crawler.ethglobal import ETHGlobalCrawler
        html = """
        <html><head>
            <meta name="description" content="ETHGlobal Lisbon 2026 hackathon">
        </head><body>
            <h1>ETHGlobal Lisbon 2026</h1>
            <main>Lisbon, Portugal. July 24-26, 2026.</main>
        </body></html>
        """
        crawler = ETHGlobalCrawler()
        data = crawler._parse_detail_html(html, "https://ethglobal.com/events/lisbon2026")
        assert data["title"] == "ETHGlobal Lisbon 2026"
        assert "Lisbon" in data.get("description", "")
        assert data["organizer"] == "ETHGlobal"
        assert "Web3" in data["tracks"]

    def test_missing_heading_does_not_invent_title_from_url(self):
        from app.crawler.ethglobal import ETHGlobalCrawler

        data = ETHGlobalCrawler()._parse_detail_html(
            "<html><body><main>Event details unavailable</main></body></html>",
            "https://ethglobal.com/events/lisbon2026",
        )

        assert "title" not in data

    def test_platform_name(self):
        """测试平台名称"""
        from app.crawler.ethglobal import ethglobal_crawler
        assert ethglobal_crawler.platform_name == "ethglobal"


# ── Hackathon.com 爬虫测试 ──────────────────────────

class TestHackathonComCrawler:
    def test_parse_list_html(self):
        """测试解析 Hackathon.com 列表页"""
        from app.crawler.hackathon_com import HackathonComCrawler
        html = """
        <html><body>
            <a href="/event/csu-ai-hackathon-6994d99bcda1f3c27a04bfb9">CSU AI Hackathon</a>
            <a href="/event/nccu-ai-hackathon-699f2942b819d897854166c4">NCCU AI Hackathon</a>
            <a href="https://corporate.hackathon.com/">Corporate</a>
        </body></html>
        """
        crawler = HackathonComCrawler()
        urls = crawler._parse_list_html(html)
        assert len(urls) == 2
        assert "https://www.hackathon.com/event/csu-ai-hackathon-6994d99bcda1f3c27a04bfb9" in urls

    def test_parse_detail_html_extracts_organizer(self):
        """测试提取组织者信息"""
        from app.crawler.hackathon_com import HackathonComCrawler
        html = """
        <html><body>
            <h1>CSU AI Hackathon</h1>
            <p>Organized by IBM SkillsBuild. In-person only. Student.</p>
            <p>January 15, 2026 to January 17, 2026</p>
        </body></html>
        """
        crawler = HackathonComCrawler()
        data = crawler._parse_detail_html(html, "https://www.hackathon.com/event/test")
        assert data["title"] == "CSU AI Hackathon"
        assert data.get("mode") == "offline"  # "In-person" → offline
        assert "IBM" in data.get("organizer", "")

    def test_parse_detail_html_extracts_dates(self):
        """测试提取日期"""
        from app.crawler.hackathon_com import HackathonComCrawler
        html = """
        <html><body>
            <h1>Test Hackathon</h1>
            <p>March 10, 2026 to March 12, 2026</p>
        </body></html>
        """
        crawler = HackathonComCrawler()
        data = crawler._parse_detail_html(html, "https://www.hackathon.com/event/test")
        assert "March" in data.get("start_date", "")

    def test_unrelated_page_dates_are_not_used_as_event_range(self):
        from app.crawler.hackathon_com import HackathonComCrawler

        html = """
        <html><body>
            <h1>Test Hackathon</h1>
            <p>Published 2026-01-01</p>
            <p>Article updated 2026-02-02</p>
        </body></html>
        """

        data = HackathonComCrawler()._parse_detail_html(
            html, "https://www.hackathon.com/event/test"
        )

        assert "start_date" not in data
        assert "end_date" not in data

    def test_labeled_publication_range_is_not_used_as_event_range(self):
        from app.crawler.hackathon_com import HackathonComCrawler

        html = """
        <html><body>
            <h1>Test Hackathon</h1>
            <p>Published from 2026-01-01 to 2026-01-02</p>
        </body></html>
        """

        data = HackathonComCrawler()._parse_detail_html(
            html, "https://www.hackathon.com/event/test"
        )

        assert "start_date" not in data
        assert "end_date" not in data

    def test_platform_name(self):
        """测试平台名称"""
        from app.crawler.hackathon_com import hackathon_com_crawler
        assert hackathon_com_crawler.platform_name == "hackathon_com"


# ── itch.io Jams 爬虫测试 ───────────────────────────

class TestItchJamsCrawler:
    def test_parse_list_html(self):
        """测试解析 itch.io Jams 列表页"""
        from app.crawler.itch_jams import ItchJamsCrawler
        html = """
        <html><body>
            <a href="/jam/gmtk-jam-2026">GMTK Game Jam 2026</a>
            <a href="/jam/brackeys-16">Brackeys Game Jam 2026.2</a>
            <a href="/jam/kenney-jam-2026">Kenney Jam 2026</a>
            <a href="/jam/gbjam-14/submissions">Submissions</a>
        </body></html>
        """
        crawler = ItchJamsCrawler()
        urls = crawler._parse_list_html(html)
        # /jam/gbjam-14/submissions 应被排除（有子路径）
        assert len(urls) == 3
        assert "https://itch.io/jam/gmtk-jam-2026" in urls
        assert "https://itch.io/jam/brackeys-16" in urls

    def test_parse_detail_html_extracts_dates(self):
        """测试提取 ISO 日期"""
        from app.crawler.itch_jams import ItchJamsCrawler
        html = """
        <html><body>
            <div class="date_range">Submissions open from 2026-07-22 17:00:00 to 2026-07-26 17:00:00</div>
            <div class="jam_content">GMTK Game Jam 2026 description</div>
        </body></html>
        """
        crawler = ItchJamsCrawler()
        data = crawler._parse_detail_html(html, "https://itch.io/jam/gmtk-jam-2026")
        assert data["start_date"] == "2026-07-22 17:00:00"
        assert data["end_date"] == "2026-07-26 17:00:00"
        assert data["mode"] == "online"
        assert "Game Development" in data["tracks"]

    def test_parse_detail_html_does_not_invent_title_from_url(self):
        """缺少官方标题时不用 URL slug 伪造标题。"""
        from app.crawler.itch_jams import ItchJamsCrawler
        html = "<html><body><h1>itch.io</h1></body></html>"
        crawler = ItchJamsCrawler()
        data = crawler._parse_detail_html(html, "https://itch.io/jam/gmtk-jam-2026")
        assert "title" not in data

    def test_parse_detail_html_participants(self):
        """测试提取参与人数"""
        from app.crawler.itch_jams import ItchJamsCrawler
        html = """
        <html><body>
            <h1>Test Jam</h1>
            <div class="date_range">2026-01-01 to 2026-01-03</div>
            <p>5,432 joined</p>
        </body></html>
        """
        crawler = ItchJamsCrawler()
        data = crawler._parse_detail_html(html, "https://itch.io/jam/test")
        assert data.get("participants_count") == 5432

    def test_platform_name(self):
        """测试平台名称"""
        from app.crawler.itch_jams import itch_jams_crawler
        assert itch_jams_crawler.platform_name == "itch_jams"


# ── 新爬虫注册测试 ──────────────────────────────────

class TestNewCrawlersRegistration:
    def test_crawlers_in_registry(self):
        """测试新爬虫已注册到 CRAWLER_REGISTRY"""
        from app.crawler.scheduler import CRAWLER_REGISTRY
        assert "ethglobal" in CRAWLER_REGISTRY
        assert "hackathon_com" in CRAWLER_REGISTRY
        assert "itch_jams" in CRAWLER_REGISTRY

    def test_crawlers_in_schedule(self):
        """测试新爬虫有调度配置"""
        from app.crawler.scheduler import CRAWL_SCHEDULE
        assert "ethglobal" in CRAWL_SCHEDULE
        assert "hackathon_com" in CRAWL_SCHEDULE
        assert "itch_jams" in CRAWL_SCHEDULE

    def test_crawlers_in_apscheduler(self):
        """测试新爬虫已注册到 APScheduler"""
        from app.crawler.apscheduler_manager import SCHEDULE_JOBS
        assert "ethglobal" in SCHEDULE_JOBS
        assert "hackathon_com" in SCHEDULE_JOBS
        assert "itch_jams" in SCHEDULE_JOBS

    def test_registered_platforms_match_supported_set(self):
        """已下线的平台不得残留在注册表中。"""
        from app.crawler.scheduler import CRAWLER_REGISTRY
        assert set(CRAWLER_REGISTRY) == {
            "dorahacks",
            "devpost",
            "mlh",
            "eventbrite",
            "saikr",
            "tianchi",
            "huodongxing",
            "ethglobal",
            "hackathon_com",
            "itch_jams",
        }


# ── HTTP 客户端复用测试 ────────────────────────────────

class TestHttpClientReuse:
    def _make_crawler(self, **kwargs):
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = "https://example.com"

            async def fetch_list(self):
                return []

            async def fetch_detail(self, url):
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="t")

        return DummyCrawler(**kwargs)

    def _mock_client_factory(self, created):
        import httpx

        def fake_build(proxy=None):
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
            )
            created.append(client)
            return client

        return fake_build

    @pytest.mark.asyncio
    async def test_safe_get_reuses_client_without_proxy_pool(self):
        crawler = self._make_crawler(max_retries=0)
        created = []
        crawler._build_client = self._mock_client_factory(created)
        try:
            resp1 = await crawler._safe_get("https://example.com/1")
            resp2 = await crawler._safe_get("https://example.com/2")
            assert resp1.status_code == 200
            assert resp2.status_code == 200
            assert len(created) == 1  # 无代理池时复用同一 client（连接池生效）
        finally:
            await crawler.close()
        assert crawler._client is None

    @pytest.mark.asyncio
    async def test_proxy_pool_still_builds_client_per_request(self):
        crawler = self._make_crawler(max_retries=0, proxy="http://p1:8080,http://p2:8080")
        created = []
        crawler._build_client = self._mock_client_factory(created)
        await crawler._safe_get("https://example.com/1")
        await crawler._safe_get("https://example.com/2")
        assert len(created) == 2  # 代理池是客户端级配置，逐请求新建以轮换代理

    def test_client_survives_event_loop_switch(self):
        import asyncio

        crawler = self._make_crawler(max_retries=0)
        created = []
        crawler._build_client = self._mock_client_factory(created)

        async def once():
            resp = await crawler._safe_get("https://example.com/1")
            assert resp.status_code == 200

        asyncio.run(once())
        asyncio.run(once())  # 第二个事件循环不应报 "attached to a different loop"
        assert len(created) == 2


# ── run() 限并发测试 ─────────────────────────────────

class TestBaseCrawlerConcurrency:
    @pytest.mark.asyncio
    async def test_run_fetches_details_concurrently(self):
        import asyncio
        import time

        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return [f"https://example.com/{i}" for i in range(6)]

            async def fetch_detail(self, url):
                await asyncio.sleep(0.1)
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="t")

        crawler = DummyCrawler(request_delay=0, max_concurrency=3)
        start = time.monotonic()
        results = await crawler.run()
        elapsed = time.monotonic() - start
        assert len(results) == 6
        assert elapsed < 0.5  # 串行需 ~0.6s，3 路并发应 ~0.2s

    @pytest.mark.asyncio
    async def test_run_preserves_url_order(self):
        import asyncio

        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return [f"https://example.com/{i}" for i in range(6)]

            async def fetch_detail(self, url):
                index = int(url.rsplit("/", 1)[1])
                await asyncio.sleep((5 - index) * 0.01)  # 完成顺序与 URL 顺序相反
                return CrawlResult(
                    source_platform="dummy", source_url=url, raw_title=f"t{index}"
                )

        crawler = DummyCrawler(request_delay=0, max_concurrency=6)
        results = await crawler.run()
        assert [r.raw_title for r in results] == [f"t{i}" for i in range(6)]

    @pytest.mark.asyncio
    async def test_run_blocked_error_stops_dispatching(self):
        class DummyCrawler(BaseCrawler):
            platform_name = "dummy"
            base_url = ""

            async def fetch_list(self):
                return [f"https://example.com/{i}" for i in range(5)]

            async def fetch_detail(self, url):
                if url.endswith("/0"):
                    raise BlockedError("blocked")
                return CrawlResult(source_platform="dummy", source_url=url, raw_title="t")

        crawler = DummyCrawler(request_delay=0, max_concurrency=1)
        results = await crawler.run()
        assert results == []  # 第一个被拦截后不再派发后续 URL


# ── CloakBrowser 锁测试 ──────────────────────────────

class TestCloakBrowserLock:
    def test_browser_lock_is_asyncio_lock(self):
        import asyncio
        from app.crawler.cloak_base import CloakBrowserBaseCrawler

        crawler = CloakBrowserBaseCrawler()
        assert isinstance(crawler._get_lock(), asyncio.Lock)

    def test_cloak_crawlers_default_to_bounded_concurrency(self):
        from app.crawler.cloak_base import CloakBrowserBaseCrawler

        assert CloakBrowserBaseCrawler().max_concurrency == 3


# ── 列表分页抓取测试 ──────────────────────────────────

class TestPagination:
    @pytest.mark.asyncio
    async def test_eventbrite_paginates_until_no_new_links(self):
        from app.crawler.eventbrite import EventbriteCrawler

        crawler = EventbriteCrawler()
        pages = {
            1: '<a href="/e/alpha-111">a</a><a href="/e/beta-222">b</a>',
            2: '<a href="/e/gamma-333">c</a>',
            3: '<a href="/e/alpha-111">a</a>',  # 全部为旧链接 → 停止
        }
        requested = []

        async def fake_get(url, **kwargs):
            page = kwargs["params"]["page"]
            requested.append(page)
            return MagicMock(text=pages.get(page, ""))

        crawler._safe_get = fake_get
        urls = await crawler.fetch_list()

        assert "https://www.eventbrite.com/e/alpha-111" in urls
        assert "https://www.eventbrite.com/e/gamma-333" in urls
        # 每个搜索路径在第 3 页（无新链接）停止，不会请求第 4 页
        assert max(requested) == 3

    @pytest.mark.asyncio
    async def test_tianchi_paginates_until_short_page(self):
        from app.crawler.tianchi import TianchiCrawler

        crawler = TianchiCrawler()
        requested = []

        async def fake_get(url, **kwargs):
            page = kwargs["params"]["page"]
            requested.append(page)
            count = 20 if page == 1 else 5  # 第 2 页为短页 → 停止
            items = [{"id": page * 100 + i} for i in range(count)]
            return MagicMock(text=json.dumps({"data": {"list": items}}))

        crawler._safe_get = fake_get
        urls = await crawler.fetch_list()

        assert requested == [1, 2]
        assert len(urls) == 25

    @pytest.mark.asyncio
    async def test_itch_paginates_to_cap_when_pages_always_have_new_links(self):
        from app.crawler.itch_jams import ItchJamsCrawler

        crawler = ItchJamsCrawler()

        async def always_new(url, **kwargs):
            page = (kwargs.get("params") or {}).get("page", 1)
            return MagicMock(text=f'<a href="/jam/jam-{page}">j</a>')

        crawler._safe_get = always_new
        urls = await crawler.fetch_list()
        assert len(urls) == crawler.MAX_PAGES

    @pytest.mark.asyncio
    async def test_itch_stops_when_page_has_no_new_links(self):
        from app.crawler.itch_jams import ItchJamsCrawler

        crawler = ItchJamsCrawler()
        pages = {
            1: '<a href="/jam/a">a</a>',
            2: '<a href="/jam/b">b</a>',
            3: '<a href="/jam/a">a</a>',  # 旧链接 → 停止
        }
        requested = []

        async def dup_get(url, **kwargs):
            page = (kwargs.get("params") or {}).get("page", 1)
            requested.append(page)
            return MagicMock(text=pages.get(page, ""))

        crawler._safe_get = dup_get
        urls = await crawler.fetch_list()

        assert urls == ["https://itch.io/jam/a", "https://itch.io/jam/b"]
        assert requested == [1, 2, 3]
