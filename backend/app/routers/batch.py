"""
Batch benchmark run: executes the full curated sample set and streams one
NDJSON line per completed question, so the frontend can populate the
scorecard table live as results come in (rather than waiting for the
whole batch to finish) -- this is what the Loom demo's "run the whole
benchmark live" moment is built on.
"""
import json
from typing import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..auth import require_demo_access
from ..db import get_session
from ..pipeline import run_pipeline
from ..sample_data import SAMPLE_QUESTIONS
from ..schemas import EvaluateRequest
from .evaluate import persist_result

router = APIRouter()


@router.post("/run-batch", dependencies=[Depends(require_demo_access)])
def run_batch(session: Session = Depends(get_session)) -> StreamingResponse:
    def stream() -> Iterator[str]:
        for sample in SAMPLE_QUESTIONS:
            request = EvaluateRequest(question=sample["question"], session_id=f"batch-{sample['id']}")
            result = run_pipeline(
                request,
                expected_risk_tier=sample["expected_risk_tier"],
                expected_guardrail_trigger=sample["expected_guardrail_trigger"],
            )
            persist_result(session, result)

            any_flag = bool(result.guardrail_evaluation and result.guardrail_evaluation.any_flag)
            severity = result.guardrail_evaluation.severity.value if result.guardrail_evaluation else "none"
            # "Correct" here means: the pipeline's end-to-end behavior
            # matched what the sample was curated to expect -- a clean
            # pass for benign questions, or a flag/fallback for the
            # riskier ones. This is the same basic idea as the published
            # benchmark's accuracy scoring, at a much smaller scale.
            triggered_something = any_flag or result.final_action.value != "passed"
            is_correct = triggered_something == bool(sample["expected_guardrail_trigger"])

            payload = {
                "id": sample["id"],
                "question": result.question,
                "risk_category": result.risk_classification.category.value,
                "final_action": result.final_action.value,
                "final_provider_model": result.final_provider_model,
                "any_flag": any_flag,
                "severity": severity,
                "expected_risk_tier": sample["expected_risk_tier"],
                "expected_guardrail_trigger": sample["expected_guardrail_trigger"],
                "is_correct": is_correct,
                "final_answer": result.final_answer,
            }
            yield json.dumps(payload) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")
