"""Export endpoints for raw and summary data downloads."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from database import DB_PATH
from routers.analytics import _where

router = APIRouter(prefix="/api/v1/export")

ALL_COLUMNS = [
    "id", "timestamp", "user_id", "course_id", "exercise_id",
    "srl_phase", "strategy", "question_text", "student_code",
    "test_results", "custom_question", "response_text", "latency_ms",
    "rating",
]

PHASES = [
    "planning", "program_creation", "error_correction", "self_reflection",
]

PHASE_CSV_HEADERS = {
    "planning": "Planning",
    "program_creation": "Program Creation",
    "error_correction": "Error Correction",
    "self_reflection": "Self-Reflection",
}

# Excel on Windows expects UTF-8 with BOM to detect encoding when opening CSV directly.
UTF8_BOM = b"\xef\xbb\xbf"


def _exercise_display_label(exercise_id: str, exercise_label: str) -> str:
    label = (exercise_label or "").strip()
    if label:
        return label
    return f"Question ID: {exercise_id}"


def _summary_csv_headers(group_by: str, distinct_label: str) -> list[str]:
    if group_by == "student":
        first, distinct = "Student", "Unique Exercises"
    elif group_by == "exercise":
        first, distinct = "Exercise", "Unique Students"
    else:
        first, distinct = "SRL Phase", "Unique Students"
    return (
        [first, "Total Interactions", distinct]
        + [PHASE_CSV_HEADERS[p] for p in PHASES]
    )


def _summary_csv_data_row(group_by: str, row: tuple) -> list:
    """Map DB row to CSV cells (readable first column for exercise grouping)."""
    cells = list(row)
    if group_by == "exercise" and len(cells) >= 2:
        group_key, exercise_label = cells[0], cells[1]
        return [_exercise_display_label(str(group_key), str(exercise_label or ""))] + cells[2:]
    return cells


def _rows_to_csv_text(headers: list[str], rows: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def _raw_export_filename(now: str, fmt: str) -> str:
    ext = "json" if fmt == "json" else "csv"
    return f"interactions_export_{now}.{ext}"


def _summary_export_filename(now: str, group_by: str, fmt: str) -> str:
    ext = "json" if fmt == "json" else "csv"
    return f"summary_by_{group_by}_{now}.{ext}"


def _build_csv_response(csv_text: str, filename: str) -> StreamingResponse:
    body_bytes = UTF8_BOM + csv_text.encode("utf-8")
    return StreamingResponse(
        iter([body_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/raw")
async def export_raw(
    course_id: Optional[str] = None,
    user_id: Optional[str] = None,
    exercise_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    format: str = Query("csv", pattern="^(csv|json)$"),
):
    where, params = _where(
        course_id=course_id,
        user_id=user_id,
        exercise_id=exercise_id,
        date_from=date_from,
        date_to=date_to,
    )
    sql = f"SELECT {', '.join(ALL_COLUMNS)} FROM interactions{where} ORDER BY id"

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(sql, params)

    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        data = [dict(zip(ALL_COLUMNS, row)) for row in rows]
        body = json.dumps(data, indent=2, ensure_ascii=False)
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{_raw_export_filename(now, "json")}"'
                ),
            },
        )

    csv_text = _rows_to_csv_text(ALL_COLUMNS, rows)
    return _build_csv_response(csv_text, _raw_export_filename(now, "csv"))


@router.get("/summary")
async def export_summary(
    course_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = Query("student", pattern="^(student|exercise|phase)$"),
    format: str = Query("csv", pattern="^(csv|json)$"),
):
    where, params = _where(
        course_id=course_id,
        date_from=date_from,
        date_to=date_to,
    )

    if group_by == "student":
        group_col = "user_id"
        count_distinct = "COUNT(DISTINCT exercise_id) AS unique_exercises"
        distinct_label = "unique_exercises"
    elif group_by == "exercise":
        group_col = "exercise_id"
        count_distinct = "COUNT(DISTINCT user_id) AS unique_students"
        distinct_label = "unique_students"
    else:  # phase
        group_col = "srl_phase"
        count_distinct = "COUNT(DISTINCT user_id) AS unique_students"
        distinct_label = "unique_students"

    phase_cases = ", ".join(
        f"SUM(CASE WHEN srl_phase = '{p}' THEN 1 ELSE 0 END) AS {p}"
        for p in PHASES
    )

    label_select = (
        ", MAX(NULLIF(exercise_label, '')) AS exercise_label"
        if group_by == "exercise"
        else ""
    )

    sql = f"""
        SELECT {group_col} AS group_key{label_select},
               COUNT(*) AS total_interactions,
               {count_distinct},
               {phase_cases}
        FROM interactions{where}
        GROUP BY {group_col}
        ORDER BY {group_col}
    """

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(sql, params)

    columns = ["group_key", "total_interactions", distinct_label] + PHASES
    if group_by == "exercise":
        columns = ["group_key", "exercise_label", "total_interactions", distinct_label] + PHASES

    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        data = [dict(zip(columns, row)) for row in rows]
        body = json.dumps(data, indent=2, ensure_ascii=False)
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{_summary_export_filename(now, group_by, "json")}"'
                ),
            },
        )

    csv_headers = _summary_csv_headers(group_by, distinct_label)
    csv_rows = [_summary_csv_data_row(group_by, row) for row in rows]
    csv_text = _rows_to_csv_text(csv_headers, csv_rows)
    return _build_csv_response(csv_text, _summary_export_filename(now, group_by, "csv"))
