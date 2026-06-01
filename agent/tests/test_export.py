"""Tests for export endpoints."""
from __future__ import annotations

import csv
import io
import json
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
    ("2026-03-10T09:00:00Z", "s1", "c1", "q1", "planning", "general",
     "What is X?", "print('hello')", "OK", "", "Try thinking about...", 1200),
    ("2026-03-10T10:00:00Z", "s1", "c1", "q1", "error_correction", "error_diagnosis",
     "Fix bug", "x = 1\ny = x + '2'", "FAIL", "", "Check types", 1800),
    ("2026-03-11T09:00:00Z", "s2", "c1", "q2", "planning", "problem_decomposition",
     "How?", "# no code", "", "", "Break it down", 1500),
]


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create a fresh DB with seed data for each test."""
    await init_db()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        for row in SEED_ROWS:
            (ts, uid, cid, eid, phase, strategy,
             q_text, code, results, custom, response, latency) = row
            await db.execute(
                """
                INSERT INTO interactions
                    (timestamp, user_id, course_id, exercise_id,
                     srl_phase, strategy, question_text, student_code,
                     test_results, custom_question, response_text, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, uid, cid, eid, phase, strategy,
                 q_text, code, results, custom, response, latency),
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


BASE = "/api/v1/export"


def _decode_csv_response(resp: httpx.Response) -> str:
    assert resp.content.startswith(b"\xef\xbb\xbf"), "CSV must start with UTF-8 BOM"
    return resp.content.decode("utf-8-sig")


@pytest.mark.asyncio
async def test_export_raw_csv(client):
    resp = await client.get(f"{BASE}/raw")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "charset=utf-8" in resp.headers["content-type"]
    assert "interactions_export_" in resp.headers.get("content-disposition", "")
    assert ".csv" in resp.headers.get("content-disposition", "")
    reader = csv.reader(io.StringIO(_decode_csv_response(resp)))
    rows = list(reader)
    # header + 3 data rows
    assert len(rows) == 4
    header = rows[0]
    code_idx = header.index("student_code")
    assert rows[1][code_idx] == "print('hello')"
    # Row with newline in student_code should be properly quoted
    assert rows[2][code_idx] == "x = 1\ny = x + '2'"


@pytest.mark.asyncio
async def test_export_raw_json(client):
    resp = await client.get(f"{BASE}/raw", params={"format": "json"})
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert len(data) == 3
    assert data[0]["student_code"] == "print('hello')"
    assert data[1]["student_code"] == "x = 1\ny = x + '2'"


@pytest.mark.asyncio
async def test_export_raw_filtered(client):
    resp = await client.get(f"{BASE}/raw", params={"user_id": "s1"})
    assert resp.status_code == 200
    reader = csv.reader(io.StringIO(_decode_csv_response(resp)))
    rows = list(reader)
    # header + 2 data rows for s1
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_export_summary_by_student(client):
    resp = await client.get(f"{BASE}/summary", params={"format": "json", "group_by": "student"})
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert len(data) == 2  # s1, s2
    s1 = [d for d in data if d["group_key"] == "s1"][0]
    assert s1["total_interactions"] == 2
    assert s1["unique_exercises"] == 1
    assert s1["planning"] == 1
    assert s1["error_correction"] == 1
    s2 = [d for d in data if d["group_key"] == "s2"][0]
    assert s2["total_interactions"] == 1
    assert s2["planning"] == 1


@pytest.mark.asyncio
async def test_export_summary_by_exercise(client):
    resp = await client.get(f"{BASE}/summary", params={"format": "json", "group_by": "exercise"})
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert len(data) == 2  # q1, q2
    q1 = [d for d in data if d["group_key"] == "q1"][0]
    assert q1["total_interactions"] == 2
    assert q1["unique_students"] == 1
    q2 = [d for d in data if d["group_key"] == "q2"][0]
    assert q2["total_interactions"] == 1
    assert q2["unique_students"] == 1


@pytest.mark.asyncio
async def test_raw_export_includes_rating_column():
    """CSV export must contain a 'rating' column."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/export/raw?format=csv")
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(_decode_csv_response(resp)))
    assert "rating" in reader.fieldnames


@pytest.mark.asyncio
async def test_export_summary_csv_has_utf8_bom(client):
    resp = await client.get(f"{BASE}/summary", params={"format": "csv", "group_by": "student"})
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xef\xbb\xbf")
    assert "charset=utf-8" in resp.headers["content-type"]
    assert "summary_by_student_" in resp.headers.get("content-disposition", "")
    reader = csv.reader(io.StringIO(_decode_csv_response(resp)))
    rows = list(reader)
    assert rows[0] == [
        "Student",
        "Total Interactions",
        "Unique Exercises",
        "Planning",
        "Program Creation",
        "Error Correction",
        "Self-Reflection",
    ]
    assert len(rows) >= 2  # header + at least one student group


@pytest.mark.asyncio
async def test_export_summary_csv_headers_by_group(client):
    student_resp = await client.get(
        f"{BASE}/summary", params={"format": "csv", "group_by": "student"}
    )
    student_rows = list(csv.reader(io.StringIO(_decode_csv_response(student_resp))))
    assert student_rows[0][0] == "Student"

    exercise_resp = await client.get(
        f"{BASE}/summary", params={"format": "csv", "group_by": "exercise"}
    )
    exercise_rows = list(csv.reader(io.StringIO(_decode_csv_response(exercise_resp))))
    assert exercise_rows[0][0] == "Exercise"

    phase_resp = await client.get(
        f"{BASE}/summary", params={"format": "csv", "group_by": "phase"}
    )
    phase_rows = list(csv.reader(io.StringIO(_decode_csv_response(phase_resp))))
    assert phase_rows[0][0] == "SRL Phase"


@pytest.mark.asyncio
async def test_export_summary_csv_exercise_uses_label(client):
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
                "2026-03-12T10:00:00Z", "s1", "c1", "q99", "Binary Search Intro",
                "planning", "general", "Q", "code", "OK", "", "resp", 500,
            ),
        )
        await db.commit()

    resp = await client.get(f"{BASE}/summary", params={"format": "csv", "group_by": "exercise"})
    rows = list(csv.reader(io.StringIO(_decode_csv_response(resp))))
    labels = [r[0] for r in rows[1:]]
    assert "Binary Search Intro" in labels
    assert "Question ID: q1" in labels  # seed row without exercise_label


@pytest.mark.asyncio
async def test_export_raw_csv_preserves_unicode(client):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO interactions
                (timestamp, user_id, course_id, exercise_id,
                 srl_phase, strategy, question_text, student_code,
                 test_results, custom_question, response_text, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-12T09:00:00Z", "s_unicode", "c1", "q_unicode",
                "planning", "general", "中文テスト", "print('你好')",
                "OK", "", "日本語の回答", 900,
            ),
        )
        await db.commit()

    resp = await client.get(f"{BASE}/raw")
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(_decode_csv_response(resp)))
    match = [r for r in reader if r["user_id"] == "s_unicode"]
    assert len(match) == 1
    assert match[0]["question_text"] == "中文テスト"
    assert match[0]["response_text"] == "日本語の回答"
    assert match[0]["student_code"] == "print('你好')"
