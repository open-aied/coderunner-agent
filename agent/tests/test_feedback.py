"""Tests for the Responses API feedback flow and session chaining."""
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

from database import DB_PATH, fetch_last_response_id, init_db
import services.llm as llm
from main import app

EN_SESSION_KEY = "student-question:s1:q1:lang:English"
JA_SESSION_KEY = "student-question:s1:q1:lang:Japanese"
ZH_SESSION_KEY = "student-question:s1:q1:lang:Chinese"


class FakeResponse:
    def __init__(self, response_id: str | None, output_text: str):
        self.id = response_id
        self.output_text = output_text


class FakeResponsesAPI:
    def __init__(self, queued_responses: list[FakeResponse]):
        self.calls: list[dict] = []
        self._queued = list(queued_responses)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._queued:
            raise AssertionError("Unexpected extra Responses API call")
        return self._queued.pop(0)


class FakeClient:
    def __init__(self, queued_responses: list[FakeResponse]):
        self.responses = FakeResponsesAPI(queued_responses)


def install_fake_client(responses: list[FakeResponse]) -> FakeClient:
    fake = FakeClient(responses)
    llm.client = fake
    return fake


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        await db.execute("DELETE FROM response_sessions")
        await db.commit()
    llm.client = None
    yield
    llm.client = None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM interactions")
        await db.execute("DELETE FROM response_sessions")
        await db.commit()


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


def build_feedback_payload(**overrides):
    payload = {
        "user_id": "s1",
        "course_id": "c1",
        "exercise_id": "q1",
        "session_key": "student-question:s1:q1",
        "question_text": "Write a loop.",
        "student_code": "print('hi')",
        "test_results": "FAIL",
        "expected_output": "hello",
        "srl_phase": "planning",
        "strategy": "general",
        "custom_question": "",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_feedback_starts_new_session_and_persists_response_id(client):
    fake = install_fake_client([FakeResponse("resp_1", "Helpful text")])

    resp = await client.post("/api/v1/feedback", json=build_feedback_payload())

    assert resp.status_code == 200
    assert resp.json()["feedback"] == "Helpful text"
    assert len(fake.responses.calls) == 1
    call = fake.responses.calls[0]
    assert call["model"] == "gpt-5.4-mini-2026-03-17"
    assert call["store"] is True
    assert call["reasoning"] == {"effort": "none"}
    assert call["max_output_tokens"] == 600
    assert "instructions" in call
    assert "Response language: Write the entire feedback in English." in call["instructions"]
    assert "previous_response_id" not in call
    assert await fetch_last_response_id(EN_SESSION_KEY) == "resp_1"

    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            """
            SELECT session_key, previous_response_id, openai_response_id, preferred_language
            FROM interactions
            ORDER BY id DESC
            LIMIT 1
            """
        )
    assert row[0][0] == EN_SESSION_KEY
    assert row[0][1] is None
    assert row[0][2] == "resp_1"
    assert row[0][3] == ""


@pytest.mark.asyncio
async def test_feedback_reuses_previous_response_id_on_follow_up_turn(client):
    fake = install_fake_client(
        [
            FakeResponse("resp_1", "First answer"),
            FakeResponse("resp_2", "Second answer"),
        ]
    )

    first = await client.post("/api/v1/feedback", json=build_feedback_payload())
    second = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(student_code="print('bye')", srl_phase="error_correction"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(fake.responses.calls) == 2
    assert "instructions" in fake.responses.calls[0]
    assert "instructions" in fake.responses.calls[1]
    assert fake.responses.calls[1]["previous_response_id"] == "resp_1"
    assert await fetch_last_response_id(EN_SESSION_KEY) == "resp_2"


@pytest.mark.asyncio
async def test_feedback_accepts_missing_session_key_without_chaining(client):
    fake = install_fake_client([FakeResponse("resp_1", "Helpful text")])

    resp = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(session_key=None),
    )

    assert resp.status_code == 200
    assert len(fake.responses.calls) == 1
    assert "previous_response_id" not in fake.responses.calls[0]

    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall("SELECT COUNT(*) FROM response_sessions")
    assert row[0][0] == 0


@pytest.mark.asyncio
async def test_feedback_accepts_preferred_language(client):
    fake = install_fake_client([FakeResponse("resp_1", "Helpful text")])

    resp = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="zh_cn"),
    )

    assert resp.status_code == 200
    assert "Response language: Write the entire feedback in Chinese." in fake.responses.calls[0]["instructions"]
    assert await fetch_last_response_id(ZH_SESSION_KEY) == "resp_1"


@pytest.mark.asyncio
async def test_feedback_does_not_reuse_previous_response_id_across_languages(client):
    fake = install_fake_client(
        [
            FakeResponse("resp_ja_1", "Japanese answer"),
            FakeResponse("resp_zh_1", "Chinese answer"),
        ]
    )

    first = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="ja"),
    )
    second = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="zh_cn"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert "previous_response_id" not in fake.responses.calls[0]
    assert "previous_response_id" not in fake.responses.calls[1]
    assert await fetch_last_response_id(JA_SESSION_KEY) == "resp_ja_1"
    assert await fetch_last_response_id(ZH_SESSION_KEY) == "resp_zh_1"

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT session_key, preferred_language
            FROM interactions
            ORDER BY id
            """
        )
    assert rows == [(JA_SESSION_KEY, "ja"), (ZH_SESSION_KEY, "zh_cn")]


@pytest.mark.asyncio
async def test_feedback_reuses_previous_response_id_when_switching_back_to_language(client):
    fake = install_fake_client(
        [
            FakeResponse("resp_ja_1", "First Japanese answer"),
            FakeResponse("resp_zh_1", "Chinese answer"),
            FakeResponse("resp_ja_2", "Second Japanese answer"),
        ]
    )

    first = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="ja"),
    )
    second = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="zh_cn"),
    )
    third = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="ja", student_code="print('again')"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert "previous_response_id" not in fake.responses.calls[0]
    assert "previous_response_id" not in fake.responses.calls[1]
    assert fake.responses.calls[2]["previous_response_id"] == "resp_ja_1"
    assert await fetch_last_response_id(JA_SESSION_KEY) == "resp_ja_2"
    assert await fetch_last_response_id(ZH_SESSION_KEY) == "resp_zh_1"


@pytest.mark.asyncio
async def test_feedback_rejects_removed_self_monitoring_phase(client):
    resp = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(srl_phase="self_monitoring"),
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_returns_502_for_empty_output_text(client):
    install_fake_client([FakeResponse("resp_1", "   ")])

    resp = await client.post("/api/v1/feedback", json=build_feedback_payload())

    assert resp.status_code == 502
    assert "Empty output_text" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_feedback_rewrites_code_blocks_without_overwriting_session_state(client):
    fake = install_fake_client(
        [
            FakeResponse("resp_1", "```python\nprint('x')\n```"),
            FakeResponse("guard_1", "- Describe the loop\n- Check the variables"),
        ]
    )

    resp = await client.post(
        "/api/v1/feedback",
        json=build_feedback_payload(preferred_language="zh_cn"),
    )

    assert resp.status_code == 200
    assert resp.json()["feedback"] == "- Describe the loop\n- Check the variables"
    assert len(fake.responses.calls) == 2
    assert "previous_response_id" not in fake.responses.calls[0]
    assert "previous_response_id" not in fake.responses.calls[1]
    assert "Write the rewritten answer entirely in Chinese." in fake.responses.calls[1]["instructions"]
    assert await fetch_last_response_id(ZH_SESSION_KEY) == "resp_1"

    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT openai_response_id FROM interactions ORDER BY id DESC LIMIT 1"
        )
    assert row[0][0] == "resp_1"
