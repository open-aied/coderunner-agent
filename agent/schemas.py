from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional

SRLPhase = Literal[
    "planning",
    "program_creation",
    "error_correction",
    "self_reflection",
]


class FeedbackRequest(BaseModel):
    user_id: str = "anonymous"
    course_id: str = ""
    exercise_id: str = ""
    exercise_label: str = ""
    session_key: Optional[str] = None
    question_text: str
    student_code: str = ""
    test_results: str = ""
    expected_output: str = ""
    srl_phase: SRLPhase = "planning"
    strategy: str = "general"
    preferred_language: str = ""
    custom_question: str = ""  # legacy, not used from UI


class FeedbackResponse(BaseModel):
    interaction_id: int
    feedback: str
    phase: str
    strategy: str
    latency_ms: int


class RatingRequest(BaseModel):
    rating: Optional[Literal['up', 'down']] = None


class RatingResponse(BaseModel):
    interaction_id: int
    rating: Optional[Literal['up', 'down']] = None


class LogEntry(BaseModel):
    id: int
    timestamp: str
    user_id: str
    course_id: str
    exercise_id: str
    srl_phase: str
    strategy: str
    latency_ms: int


# ── Analytics schemas ────────────────────────────────────────────


class DateRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")


class OverviewResponse(BaseModel):
    total_interactions: int
    unique_students: int
    unique_exercises: int
    avg_latency_ms: int
    date_range: DateRange
    thumbs_up: int = 0
    thumbs_down: int = 0
    satisfaction_pct: Optional[float] = None


class PhaseCount(BaseModel):
    phase: str
    count: int
    percentage: float


class TimelineEntry(BaseModel):
    date: str
    count: int
    unique_students: int


class ExerciseHeatmapEntry(BaseModel):
    exercise_id: str
    exercise_label: str = ""
    total: int
    by_phase: dict[str, int]


class StrategyCount(BaseModel):
    strategy: str
    count: int


class PhaseStrategyEntry(BaseModel):
    phase: str
    strategies: list[StrategyCount]


class StudentSummary(BaseModel):
    user_id: str
    total_interactions: int
    top_phase: str
    unique_exercises: int
    last_active: str


class StudentListResponse(BaseModel):
    total: int
    students: list[StudentSummary]


class StudentInteraction(BaseModel):
    id: int
    timestamp: str
    exercise_id: str
    exercise_label: str = ""
    srl_phase: str
    strategy: str
    latency_ms: int


class StudentDetailResponse(BaseModel):
    user_id: str
    total_interactions: int
    phase_distribution: list[PhaseCount]
    interactions: list[StudentInteraction]
