from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth import require_demo_access
from ..db import RunLog, get_session

router = APIRouter()


@router.get("/history", dependencies=[Depends(require_demo_access)])
def get_history(limit: int = 50, session: Session = Depends(get_session)) -> list[dict]:
    """Most recent runs (single-question and batch), most recent first."""
    statement = select(RunLog).order_by(RunLog.id.desc()).limit(limit)
    rows = session.exec(statement).all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "session_id": r.session_id,
            "question": r.question,
            "risk_category": r.risk_category,
            "final_action": r.final_action,
            "final_provider_model": r.final_provider_model,
            "any_flag": any(
                [
                    r.missed_urgency,
                    r.inappropriate_recommendation,
                    r.incorrect_treatment_advice,
                    r.missing_critical_info,
                ]
            ),
            "severity": r.severity,
            "expected_risk_tier": r.expected_risk_tier,
            "expected_guardrail_trigger": r.expected_guardrail_trigger,
        }
        for r in rows
    ]
