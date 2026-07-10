"""用户画像/EDM/个性化推荐端到端测试（走真实本地 Postgres 测试库）。

覆盖「把 user_service / edm_service / recommendation_service 从 Mock 迁到真库」：
真实注册用户（不在 MOCK_USERS 里）也能存标签、订阅 EDM，且标签能驱动推荐。
"""
import os
import subprocess

REG = {"email": "tagger@example.com", "username": "tagger", "password": "pw123456"}


def _db_scalar(sql: str) -> str:
    """在测试库执行查询返回单值文本（真库校验，绕开可能读 Mock 的 HTTP 层）。"""
    out = subprocess.run(
        ["docker", "exec", "-e", "PGPASSWORD=postgres", "hackthon-pg",
         "psql", "-U", "postgres", "-d", "hackathon_test", "-t", "-A", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def _register(client, **overrides):
    payload = {**REG, **overrides}
    r = client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    return data["access_token"], data["user"]["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_save_tags_persists_for_real_db_user(client):
    """真实 DB 用户 PUT /users/me/tags 应把标签写进真库 users 行（而非仅改 Mock 内存）。"""
    token, uid = _register(client)
    tags = {"tech_stack": ["Python", "Swift"], "interests": ["AI", "Cloud Native"], "status": "student"}

    r = client.put("/api/v1/users/me/tags", json=tags, headers=_auth(token))
    assert r.status_code == 200, r.text
    saved = r.json()["data"]["profile_tags"]
    assert set(saved["interests"]) == {"AI", "Cloud Native"}

    # 真库校验：直接查 users 行，证明确实持久化（Mock 写不会落库）
    db_tags = _db_scalar(f"SELECT profile_tags FROM users WHERE id={uid};")
    assert db_tags and db_tags != "", "标签未写入真库（疑似只改了 Mock 内存）"
    assert "Cloud Native" in db_tags and "Swift" in db_tags, f"真库标签内容不符: {db_tags}"


def test_edm_subscribe_persists_for_real_db_user(client):
    """真实 DB 用户订阅 EDM 应把 edm_subscribed 写进真库 users 行。"""
    token, uid = _register(client)

    r = client.put("/api/v1/users/me/edm-subscribe", json={"subscribed": True}, headers=_auth(token))
    assert r.status_code == 200, r.text

    db_val = _db_scalar(f"SELECT edm_subscribed FROM users WHERE id={uid};")
    assert db_val == "t", f"EDM 订阅未写入真库（Mock 写不会落库）: {db_val!r}"


def _seed_hackathons():
    """插入两条赛事。用独立 async 引擎避免跨循环。

    - AI 赛事：已结束(无状态分)、AI 赛道、高浏览量(会排在热门榜首位)。
    - Retro 赛事：报名中、Gaming 赛道、零浏览量。
    这样「个性化(读 DB 标签=Gaming)」→ 只出 Retro；「回落热门榜」→ AI 在榜。
    """
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from app.models.hackathon import Hackathon, HackathonStatus, HackathonMode

    async def _run():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        async with AsyncSession(eng) as s:
            s.add(Hackathon(
                name="AI Agents Hack", slug="ai-agents-hack",
                source_url="https://x/ai", source_platform="devpost",
                status=HackathonStatus.ENDED, mode=HackathonMode.ONLINE,
                track_tags=["AI"], tech_tags=["Python"], view_count=100,
            ))
            s.add(Hackathon(
                name="Retro Gaming Jam", slug="retro-gaming-jam",
                source_url="https://x/game", source_platform="devpost",
                status=HackathonStatus.REGISTERING, mode=HackathonMode.ONLINE,
                track_tags=["Gaming"], tech_tags=["C++"], view_count=0,
            ))
            await s.commit()
        await eng.dispose()

    asyncio.run(_run())


def test_saved_tags_drive_personalized_recommendations(client):
    """真实 DB 用户(id 不在 MOCK_USERS 内)存的标签应真正驱动 /for-you 个性化。

    注册 4 个用户，用第 4 个（id=4，避开 Mock 里的 1/2/3）。存兴趣=Gaming：
    个性化命中 Retro、AI(已结束无匹配)被过滤；若仍读 Mock 则 id=4 查无→回落热门榜→AI 在榜。
    """
    for i in range(3):
        _register(client, email=f"filler{i}@example.com", username=f"filler{i}")
    token, uid = _register(client)
    assert uid == 4, f"预期第 4 个用户 id=4，实际 {uid}"

    client.put("/api/v1/users/me/tags", json={"interests": ["Gaming"]}, headers=_auth(token))
    _seed_hackathons()

    r = client.get("/api/v1/recommendations/for-you", headers=_auth(token))
    assert r.status_code == 200, r.text
    names = [h["name"] for h in r.json()["data"]]
    assert "Retro Gaming Jam" in names, f"个性化推荐应命中 Gaming 赛事: {names}"
    assert "AI Agents Hack" not in names, f"未匹配的已结束赛事不应出现(疑似回落热门榜/读 Mock): {names}"
