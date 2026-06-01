from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException, Query

from database import DB_PATH
from schemas import (
    DateRange,
    ExerciseHeatmapEntry,
    OverviewResponse,
    PhaseCount,
    PhaseStrategyEntry,
    StrategyCount,
    StudentDetailResponse,
    StudentInteraction,
    StudentListResponse,
    StudentSummary,
    TimelineEntry,
)

router = APIRouter(prefix="/api/v1/analytics")


# ── helpers ──────────────────────────────────────────────────────


def _build_date_filter(
    col: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[list[str], list[str]]:
    """Return (clauses, params) for date range filtering."""
    clauses: list[str] = []
    params: list[str] = []
    if date_from:
        clauses.append(f"{col} >= ?")
        params.append(f"{date_from}T00:00:00")
    if date_to:
        # exclusive next day
        try:
            next_day = (
                datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ).strftime("%Y-%m-%d")
        except ValueError:
            next_day = date_to
        clauses.append(f"{col} < ?")
        params.append(f"{next_day}T00:00:00")
    return clauses, params


def _where(
    *,
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exercise_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> tuple[str, list[str]]:
    """Build a WHERE clause from common filter params."""
    clauses: list[str] = []
    params: list[str] = []

    if course_id:
        clauses.append("course_id = ?")
        params.append(course_id)
    if exercise_id:
        clauses.append("exercise_id = ?")
        params.append(exercise_id)
    if user_id:
        clauses.append("user_id = ?")
        params.append(user_id)

    date_clauses, date_params = _build_date_filter("timestamp", date_from, date_to)
    clauses.extend(date_clauses)
    params.extend(date_params)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


# ── 1. Overview ──────────────────────────────────────────────────


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    course_id: Optional[str] = None,
    date_from: Optional[str] = Query(None, alias="date_from"),
    date_to: Optional[str] = Query(None, alias="date_to"),
):
    where, params = _where(course_id=course_id, date_from=date_from, date_to=date_to)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchall(
            f"""
            SELECT
                COUNT(*)                    AS total_interactions,
                COUNT(DISTINCT user_id)     AS unique_students,
                COUNT(DISTINCT exercise_id) AS unique_exercises,
                COALESCE(AVG(latency_ms), 0) AS avg_latency_ms,
                MIN(timestamp) AS min_ts,
                MAX(timestamp) AS max_ts,
                SUM(CASE WHEN rating = 'up'   THEN 1 ELSE 0 END) AS thumbs_up,
                SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END) AS thumbs_down
            FROM interactions{where}
            """,
            params,
        )
        r = row[0]
        thumbs_up = r[6] or 0
        thumbs_down = r[7] or 0
        total_rated = thumbs_up + thumbs_down
        satisfaction_pct = (thumbs_up / total_rated * 100) if total_rated > 0 else None
        return OverviewResponse(
            total_interactions=r[0],
            unique_students=r[1],
            unique_exercises=r[2],
            avg_latency_ms=int(r[3]),
            date_range=DateRange(
                from_date=r[4] or "",
                to_date=r[5] or "",
            ),
            thumbs_up=thumbs_up,
            thumbs_down=thumbs_down,
            satisfaction_pct=round(satisfaction_pct, 1) if satisfaction_pct is not None else None,
        )


# ── 2. Phase distribution ───────────────────────────────────────


@router.get("/phase-distribution", response_model=list[PhaseCount])
async def phase_distribution(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exercise_id: Optional[str] = None,
    user_id: Optional[str] = Query(None),
):
    where, params = _where(
        course_id=course_id,
        date_from=date_from,
        date_to=date_to,
        exercise_id=exercise_id,
        user_id=user_id,
    )
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            f"SELECT srl_phase, COUNT(*) AS cnt FROM interactions{where} GROUP BY srl_phase ORDER BY cnt DESC",
            params,
        )
        total = sum(r[1] for r in rows)
        return [
            PhaseCount(
                phase=r[0],
                count=r[1],
                percentage=round(r[1] / total * 100, 1) if total else 0,
            )
            for r in rows
        ]


# ── 3. Timeline ─────────────────────────────────────────────────


@router.get("/timeline", response_model=list[TimelineEntry])
async def timeline(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    granularity: str = Query("day", pattern="^(day|week)$"),
):
    where, params = _where(course_id=course_id, date_from=date_from, date_to=date_to)

    if granularity == "week":
        date_expr = "strftime('%Y-W%W', timestamp)"
    else:
        date_expr = "DATE(timestamp)"

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            f"""
            SELECT {date_expr} AS d, COUNT(*) AS cnt,
                   COUNT(DISTINCT user_id) AS us
            FROM interactions{where}
            GROUP BY d ORDER BY d
            """,
            params,
        )
        return [
            TimelineEntry(date=r[0], count=r[1], unique_students=r[2]) for r in rows
        ]


# ── 4. Exercise heatmap ─────────────────────────────────────────


@router.get("/exercise-heatmap", response_model=list[ExerciseHeatmapEntry])
async def exercise_heatmap(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    where, params = _where(course_id=course_id, date_from=date_from, date_to=date_to)
    async with aiosqlite.connect(DB_PATH) as db:
        label_rows = await db.execute_fetchall(
            f"""
            SELECT exercise_id, MAX(NULLIF(exercise_label, '')) AS exercise_label
            FROM interactions{where}
            GROUP BY exercise_id
            """,
            params,
        )
        labels = {r[0]: (r[1] or "") for r in label_rows}

        rows = await db.execute_fetchall(
            f"""
            SELECT exercise_id, srl_phase, COUNT(*) AS cnt
            FROM interactions{where}
            GROUP BY exercise_id, srl_phase
            ORDER BY exercise_id
            """,
            params,
        )
        exercises: dict[str, ExerciseHeatmapEntry] = {}
        for r in rows:
            eid, phase, cnt = r[0], r[1], r[2]
            if eid not in exercises:
                exercises[eid] = ExerciseHeatmapEntry(
                    exercise_id=eid,
                    exercise_label=labels.get(eid, ""),
                    total=0,
                    by_phase={},
                )
            exercises[eid].by_phase[phase] = cnt
            exercises[eid].total += cnt
        return list(exercises.values())


# ── 5. Strategy usage ───────────────────────────────────────────


@router.get("/strategy-usage", response_model=list[PhaseStrategyEntry])
async def strategy_usage(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    exercise_id: Optional[str] = Query(None),
):
    where, params = _where(course_id=course_id, date_from=date_from, date_to=date_to, exercise_id=exercise_id)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            f"""
            SELECT srl_phase, strategy, COUNT(*) AS cnt
            FROM interactions{where}
            GROUP BY srl_phase, strategy
            ORDER BY srl_phase, cnt DESC
            """,
            params,
        )
        phases: dict[str, list[StrategyCount]] = {}
        for r in rows:
            phase, strategy, cnt = r[0], r[1], r[2]
            phases.setdefault(phase, []).append(
                StrategyCount(strategy=strategy, count=cnt)
            )
        return [
            PhaseStrategyEntry(phase=p, strategies=s) for p, s in phases.items()
        ]


# ── 6. Student list ─────────────────────────────────────────────


@router.get("/students", response_model=StudentListResponse)
async def students(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    where, params = _where(course_id=course_id, date_from=date_from, date_to=date_to)
    async with aiosqlite.connect(DB_PATH) as db:
        # total unique students
        total_row = await db.execute_fetchall(
            f"SELECT COUNT(DISTINCT user_id) FROM interactions{where}", params
        )
        total = total_row[0][0]

        # student summaries
        rows = await db.execute_fetchall(
            f"""
            SELECT user_id,
                   COUNT(*) AS total_interactions,
                   COUNT(DISTINCT exercise_id) AS unique_exercises,
                   MAX(timestamp) AS last_active
            FROM interactions{where}
            GROUP BY user_id
            ORDER BY total_interactions DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        )

        # find top phase per student
        user_ids = [r[0] for r in rows]
        top_phases: dict[str, str] = {}
        if user_ids:
            placeholders = ",".join("?" * len(user_ids))
            # Build filter clauses for the same date/course filters
            filter_clauses: list[str] = [f"user_id IN ({placeholders})"]
            filter_params: list[str] = list(user_ids)
            if course_id:
                filter_clauses.append("course_id = ?")
                filter_params.append(course_id)
            date_clauses, date_params = _build_date_filter("timestamp", date_from, date_to)
            filter_clauses.extend(date_clauses)
            filter_params.extend(date_params)
            filter_where = " WHERE " + " AND ".join(filter_clauses)
            phase_rows = await db.execute_fetchall(
                f"""
                SELECT user_id, srl_phase, COUNT(*) AS cnt
                FROM interactions{filter_where}
                GROUP BY user_id, srl_phase
                ORDER BY user_id, cnt DESC
                """,
                filter_params,
            )
            for pr in phase_rows:
                uid = pr[0]
                if uid not in top_phases:
                    top_phases[uid] = pr[1]

        student_list = [
            StudentSummary(
                user_id=r[0],
                total_interactions=r[1],
                top_phase=top_phases.get(r[0], ""),
                unique_exercises=r[2],
                last_active=r[3] or "",
            )
            for r in rows
        ]
        return StudentListResponse(total=total, students=student_list)


# ── 7. Student detail ───────────────────────────────────────────


@router.get("/student/{user_id}", response_model=StudentDetailResponse)
async def student_detail(
    user_id: str,
    course_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    where, params = _where(
        course_id=course_id,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
    )
    async with aiosqlite.connect(DB_PATH) as db:
        # interactions
        rows = await db.execute_fetchall(
            f"""
            SELECT id, timestamp, exercise_id, exercise_label, srl_phase, strategy, latency_ms
            FROM interactions{where}
            ORDER BY id DESC
            """,
            params,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Student not found")

        interactions = [
            StudentInteraction(
                id=r[0],
                timestamp=r[1],
                exercise_id=r[2],
                exercise_label=r[3] or "",
                srl_phase=r[4],
                strategy=r[5],
                latency_ms=r[6],
            )
            for r in rows
        ]

        # phase distribution
        phase_rows = await db.execute_fetchall(
            f"""
            SELECT srl_phase, COUNT(*) AS cnt
            FROM interactions{where}
            GROUP BY srl_phase ORDER BY cnt DESC
            """,
            params,
        )
        total = sum(r[1] for r in phase_rows)
        phase_dist = [
            PhaseCount(
                phase=r[0],
                count=r[1],
                percentage=round(r[1] / total * 100, 1) if total else 0,
            )
            for r in phase_rows
        ]

        return StudentDetailResponse(
            user_id=user_id,
            total_interactions=total,
            phase_distribution=phase_dist,
            interactions=interactions,
        )
