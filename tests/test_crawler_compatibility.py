"""Compatibility checks for integrating the crawler branch with main."""

import importlib

from sqlalchemy.dialects import postgresql


def test_crawler_package_imports_after_platform_removal():
    """Removing a crawler must not leave package-level imports behind."""
    crawler_package = importlib.import_module("app.crawler")

    assert crawler_package.CrawlerScheduler is not None


def test_all_scheduled_platforms_are_registered():
    """Every APScheduler platform job must resolve to a runnable crawler."""
    from app.crawler.apscheduler_manager import SCHEDULE_JOBS
    from app.crawler.scheduler import CRAWLER_REGISTRY

    orphaned_platforms = set(SCHEDULE_JOBS) - set(CRAWLER_REGISTRY)

    assert orphaned_platforms == set()


def test_main_application_exposes_crawler_api():
    """The merged application must keep the crawler management routes."""
    from app.main import app

    route_paths = {route.path for route in app.routes}

    assert "/api/v1/crawler/status" in route_paths


def test_merged_models_keep_postgresql_types_and_crawler_fields():
    """Conflict resolution must preserve JSONB and the crawler image column."""
    from app.models.hackathon import Hackathon
    from app.models.inspiration import InspirationItem

    team_profile_type = InspirationItem.__table__.c.team_profile.type.compile(
        dialect=postgresql.dialect()
    )

    assert str(team_profile_type) == "JSONB"
    assert "cover_image" in Hackathon.__table__.c
