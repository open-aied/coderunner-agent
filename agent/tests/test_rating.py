"""Tests for rating DB function and PATCH endpoint."""
from __future__ import annotations

import os
import sys
import tempfile

import httpx

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SQLITE_PATH"] = _tmp.name

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiosqlite
import pytest
import pytest_asyncio

from database import DB_PATH, init_db, log_interaction, update_rating


async def _seed_one() -> int:
    """Insert one interaction and return its id."""
    return await log_interaction(
        user_id="s1", course_id="c1", exercise_id="q1",
        srl_phase="planning", strategy="general",
        question_text="q", student_code="code",
        test_results="", custom_question="", response_text="r", latency_ms=100,
    )


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create a fresh DB for each test."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        await db.commit()
    yield
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        await db.commit()


@pytest.mark.asyncio
async def test_update_rating_sets_up():
    iid = await _seed_one()
    result = await update_rating(iid, "up")
    assert result is True
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT rating FROM interactions WHERE id = ?", [iid]
        )
    assert row[0][0] == "up"


@pytest.mark.asyncio
async def test_update_rating_sets_down():
    iid = await _seed_one()
    await update_rating(iid, "up")
    result = await update_rating(iid, "down")
    assert result is True
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT rating FROM interactions WHERE id = ?", [iid]
        )
    assert row[0][0] == "down"


@pytest.mark.asyncio
async def test_update_rating_clears_to_null():
    iid = await _seed_one()
    await update_rating(iid, "up")
    result = await update_rating(iid, None)
    assert result is True
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT rating FROM interactions WHERE id = ?", [iid]
        )
    assert row[0][0] is None


@pytest.mark.asyncio
async def test_update_rating_returns_false_for_missing_id():
    result = await update_rating(99999, "up")
    assert result is False


from main import app


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_patch_rating_up(client):
    iid = await _seed_one()
    resp = await client.patch(
        f"/api/v1/interactions/{iid}/rating",
        json={"rating": "up"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["interaction_id"] == iid
    assert data["rating"] == "up"


@pytest.mark.asyncio
async def test_patch_rating_toggle_to_null(client):
    iid = await _seed_one()
    await client.patch(f"/api/v1/interactions/{iid}/rating", json={"rating": "up"})
    resp = await client.patch(
        f"/api/v1/interactions/{iid}/rating", json={"rating": None}
    )
    assert resp.status_code == 200
    assert resp.json()["rating"] is None


@pytest.mark.asyncio
async def test_patch_rating_switch(client):
    iid = await _seed_one()
    await client.patch(f"/api/v1/interactions/{iid}/rating", json={"rating": "up"})
    resp = await client.patch(
        f"/api/v1/interactions/{iid}/rating", json={"rating": "down"}
    )
    assert resp.status_code == 200
    assert resp.json()["rating"] == "down"


@pytest.mark.asyncio
async def test_patch_rating_404(client):
    resp = await client.patch(
        "/api/v1/interactions/99999/rating", json={"rating": "up"}
    )
    assert resp.status_code == 404
