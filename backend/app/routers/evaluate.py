from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import require_demo_access
from ..db import RunLog, get_session
from ..pipeline import run_pipeline
from ..schemas import EvaluateRequest, EvaluationResult

router = APIRouter()


def persist_result(session: Session, result: EvaluationResult) -> None:
    guardrail = result.guardrail_evaluation
    log = RunLog(
        session_id=result.session_id,
        question=result.question,
        expected_risk_tier=result.expected_risk_tier,
        expected_guardrail_trigger=result.expected_guardrail_trigger,
        risk_category=result.risk_classification.category.value,
        risk_confidence=result.risk_classification.confidence,
        raw_primary_answer=result.raw_primary_answer,
        raw_provider_model=result.raw_provider_model,
        missed_urgency=guardrail.missed_urgency if guardrail else False,
        inappropriate_recommendation=guardrail.inappropriate_recommendation if guardrail else False,
        incorrect_treatment_advice=guardrail.incorrect_treatment_advice if guardrail else False,
        missing_critical_info=guardrail.missing_critical_info if guardrail else False,
        severity=guardrail.severity.value if guardrail else "none",
        rationale=guardrail.rationale if guardrail else result.error_detail,
        used_fallback=result.fallback_guardrail_evaluation is not None,
        final_action=result.final_action.value,
        final_answer=result.final_answer,
        final_provider_model=result.final_provider_model,
        latency_ms=result.latency_ms,
    )
    session.add(log)
    session.commit()


@router.post("/evaluate", response_model=EvaluationResult, dependencies=[Depends(require_demo_access)])
def evaluate(request: EvaluateRequest, session: Session = Depends(get_session)) -> EvaluationResult:
    """Run one question through classifier -> responder -> guardrail
    evaluator -> fallback logic, persist the run, and return the full,
    typed trace (raw answer, guardrail flags, and final answer) so the
    frontend can show a side-by-side raw-vs-guardrailed view."""
    result = run_pipeline(request)
    persist_result(session, result)
    return result
