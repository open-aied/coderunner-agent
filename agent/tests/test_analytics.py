"""Tests for analytics endpoints."""
from __future__ import annotations

import os
import sys
import tempfile

# Set SQLITE_PATH before importing any app modules
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["SQLITE_PATH"] = _tmp.name

# Add agent dir to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import aiosqlite
import pytest
import pytest_asyncio
import httpx

from database import DB_PATH, init_db
from main import app

SEED_ROWS = [
    ("2026-03-10T09:00:00Z", "s1", "c1", "q1", "planning", "general", 1200),
    ("2026-03-10T10:00:00Z", "s1", "c1", "q1", "error_correction", "error_diagnosis", 1800),
    ("2026-03-10T11:00:00Z", "s2", "c1", "q1", "error_correction", "debugging_strategy", 2200),
    ("2026-03-11T09:00:00Z", "s2", "c1", "q2", "planning", "problem_decomposition", 1500),
    ("2026-03-11T10:00:00Z", "s3", "c1", "q2", "program_creation", "knowledge_recall", 1900),
]


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create a fresh DB with seed data for each test."""
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        for row in SEED_ROWS:
            ts, uid, cid, eid, phase, strategy, latency = row
            await db.execute(
                """
                INSERT INTO interactions
                    (timestamp, user_id, course_id, exercise_id,
                     srl_phase, strategy, question_text, student_code,
                     test_results, custom_question, response_text, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts, uid, cid, eid, phase, strategy,
                    "q_text", "code", "results", "custom", "response", latency,
                ),
            )
        await db.commit()

    yield

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        await db.commit()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


BASE = "/api/v1/analytics"


@pytest.mark.asyncio
async def test_overview(client):
    resp = await client.get(f"{BASE}/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_interactions"] == 5
    assert data["unique_students"] == 3
    assert data["unique_exercises"] == 2


@pytest.mark.asyncio
async def test_overview_with_date_filter(client):
    resp = await client.get(f"{BASE}/overview", params={"date_from": "2026-03-11"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_interactions"] == 2


@pytest.mark.asyncio
async def test_phase_distribution(client):
    resp = await client.get(f"{BASE}/phase-distribution")
    assert resp.status_code == 200
    data = resp.json()
    counts = {item["phase"]: item["count"] for item in data}
    assert counts["error_correction"] == 2
    assert counts["planning"] == 2
    assert counts["program_creation"] == 1


@pytest.mark.asyncio
async def test_timeline(client):
    resp = await client.get(f"{BASE}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["count"] == 3


@pytest.mark.asyncio
async def test_exercise_heatmap(client):
    resp = await client.get(f"{BASE}/exercise-heatmap")
    assert resp.status_code == 200
    data = resp.json()
    q1 = [e for e in data if e["exercise_id"] == "q1"][0]
    assert q1["total"] == 3
    assert q1["by_phase"]["error_correction"] == 2
    assert "exercise_label" in q1


@pytest.mark.asyncio
async def test_exercise_heatmap_includes_label(client):
    import aiosqlite
    from database import DB_PATH

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO interactions
                (timestamp, user_id, course_id, exercise_id, exercise_label,
                 srl_phase, strategy, question_text, student_code,
                 test_results, custom_question, response_text, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-12T11:00:00Z", "s9", "c1", "q99", "Loop Practice",
                "planning", "general", "Q", "x=1", "OK", "", "ok", 100,
            ),
        )
        await db.commit()

    resp = await client.get(f"{BASE}/exercise-heatmap")
    entry = [e for e in resp.json() if e["exercise_id"] == "q99"][0]
    assert entry["exercise_label"] == "Loop Practice"


@pytest.mark.asyncio
async def test_strategy_usage(client):
    resp = await client.get(f"{BASE}/strategy-usage")
    assert resp.status_code == 200
    data = resp.json()
    ec = [p for p in data if p["phase"] == "error_correction"][0]
    assert len(ec["strategies"]) == 2


@pytest.mark.asyncio
async def test_students(client):
    resp = await client.get(f"{BASE}/students")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["students"][0]["total_interactions"] == 2


@pytest.mark.asyncio
async def test_student_detail(client):
    resp = await client.get(f"{BASE}/student/s1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_interactions"] == 2
    assert len(data["interactions"]) == 2


@pytest.mark.asyncio
async def test_overview_includes_rating_stats():
    """Overview returns thumbs_up, thumbs_down, satisfaction_pct."""
    # Rate the first two interactions: one up, one down
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT id FROM interactions ORDER BY id LIMIT 2"
        )
        ids = [r[0] for r in rows]
        await db.execute("UPDATE interactions SET rating = 'up' WHERE id = ?", [ids[0]])
        await db.execute("UPDATE interactions SET rating = 'down' WHERE id = ?", [ids[1]])
        await db.commit()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["thumbs_up"] == 1
    assert data["thumbs_down"] == 1
    assert data["satisfaction_pct"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_overview_satisfaction_null_when_no_ratings():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["thumbs_up"] == 0
    assert data["thumbs_down"] == 0
    assert data["satisfaction_pct"] is None
