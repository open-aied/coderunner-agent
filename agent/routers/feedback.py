import os
import time
from fastapi import APIRouter, HTTPException, Query
from schemas import FeedbackRequest, FeedbackResponse, LogEntry, RatingRequest, RatingResponse
from services.llm import build_language_session_key, get_feedback, normalize_response_language
from database import (
    fetch_last_response_id,
    fetch_logs,
    log_interaction,
    update_rating,
    upsert_response_session,
)

router = APIRouter(prefix="/api/v1")

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest):
    if not req.question_text.strip() and not req.student_code.strip():
        raise HTTPException(status_code=400, detail="question_text or student_code is required")

    response_language = normalize_response_language(req.preferred_language)
    effective_session_key = build_language_session_key(req.session_key, response_language)
    previous_response_id = await fetch_last_response_id(effective_session_key)
    t0 = time.monotonic()
    try:
        result, openai_response_id = await get_feedback(
            question_text=req.question_text,
            student_code=req.student_code,
            test_results=req.test_results,
            expected_output=req.expected_output,
            srl_phase=req.srl_phase,
            strategy=req.strategy,
            custom_question=req.custom_question,
            preferred_language=req.preferred_language,
            model=MODEL,
            previous_response_id=previous_response_id,
            response_language=response_language,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    latency_ms = int((time.monotonic() - t0) * 1000)

    interaction_id = await log_interaction(
        user_id=req.user_id,
        course_id=req.course_id,
        exercise_id=req.exercise_id,
        srl_phase=req.srl_phase,
        strategy=req.strategy,
        question_text=req.question_text,
        student_code=req.student_code,
        test_results=req.test_results,
        custom_question=req.custom_question,
        response_text=result,
        latency_ms=latency_ms,
        session_key=effective_session_key,
        previous_response_id=previous_response_id,
        openai_response_id=openai_response_id,
        preferred_language=req.preferred_language,
        exercise_label=req.exercise_label,
    )
    await upsert_response_session(
        session_key=effective_session_key,
        user_id=req.user_id,
        course_id=req.course_id,
        exercise_id=req.exercise_id,
        last_response_id=openai_response_id,
    )

    return FeedbackResponse(
        interaction_id=interaction_id,
        feedback=result,
        phase=req.srl_phase,
        strategy=req.strategy,
        latency_ms=latency_ms,
    )


@router.get("/logs", response_model=list[LogEntry])
async def logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await fetch_logs(limit=limit, offset=offset)


@router.get("/phases")
async def phases():
    from services.llm import PHASE_STRATEGIES, STRATEGY_QUESTIONS
    return {"phases": PHASE_STRATEGIES, "questions": STRATEGY_QUESTIONS}


@router.patch("/interactions/{interaction_id}/rating", response_model=RatingResponse)
async def rate_interaction(interaction_id: int, req: RatingRequest):
    found = await update_rating(interaction_id, req.rating)
    if not found:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return RatingResponse(interaction_id=interaction_id, rating=req.rating)
