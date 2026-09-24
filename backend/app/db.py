"""
Persistence layer.

SQLite by default (zero external infra, per the "don't add infrastructure
unless necessary" build rule) via SQLModel, which keeps the row model and
API schemas in the same Pydantic-flavored style used everywhere else in
this project.
"""
from datetime import datetime
from typing import Generator, Optional

from sqlmodel import Field, Session, SQLModel, create_engine

from .config import get_settings

_settings = get_settings()

_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, connect_args=_connect_args)


class RunLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: str
    question: str

    expected_risk_tier: Optional[str] = None
    expected_guardrail_trigger: Optional[bool] = None

    risk_category: str
    risk_confidence: float

    raw_primary_answer: str
    raw_provider_model: str

    missed_urgency: bool = False
    inappropriate_recommendation: bool = False
    incorrect_treatment_advice: bool = False
    missing_critical_info: bool = False
    severity: str = "none"
    rationale: Optional[str] = None

    used_fallback: bool = False

    final_action: str
    final_answer: str
    final_provider_model: str
    latency_ms: int


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
