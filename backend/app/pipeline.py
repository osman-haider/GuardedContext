"""
Orchestration: classifier -> responder -> guardrail evaluator, with a
three-tier fallback decision, matching the architecture described in
saela-demo-buildplan.md section 17.

Tier 1 (passed): primary answer clears the guardrail check -> shown as-is.
Tier 2 (provider_fallback_passed / safe_template): guardrail flags a
    high-severity issue -> regenerate once, more conservatively, optionally
    against a different provider/model (FALLBACK_MODEL_NAME) -> re-check.
    If the second attempt still fails, fall back to a safe templated
    response and log (not show) the original.
Tier 3 (provider_error): any API/parsing failure at any step -> safe
    templated response, logged distinctly from a content-safety failure.
"""
import time
import uuid

from .config import get_settings
from . import llm_client
from .schemas import (
    EvaluateRequest,
    EvaluationResult,
    FinalAction,
    RiskCategory,
    RiskClassification,
    Severity,
    UserContext,
)

SAFE_TEMPLATE_ANSWER = (
    "I want to make sure you get the right support for this. Based on what you've "
    "described, please reach out to a doctor, a nurse line, or urgent care promptly "
    "rather than waiting on an app-based explanation -- they'll be able to properly "
    "assess what's going on. I'm not able to safely interpret this particular "
    "situation on my own."
)

# These three flags map to the WHB benchmark's medically-consequential
# error types. "missing_critical_info" alone (with no other flag) is
# treated as a softer signal and does not by itself force a fallback --
# it's logged, but a merely-incomplete-but-safe answer isn't suppressed.
HARD_FALLBACK_FLAGS = ("missed_urgency", "inappropriate_recommendation", "incorrect_treatment_advice")


def _context_summary(context: UserContext | None) -> str:
    if not context:
        return ""
    parts = []
    if context.cycle_phase:
        parts.append(f"cycle phase: {context.cycle_phase}")
    if context.recent_symptoms:
        parts.append(f"recent symptoms: {context.recent_symptoms}")
    if context.sleep_summary:
        parts.append(f"sleep: {context.sleep_summary}")
    return "; ".join(parts)


def _is_hard_failure(evaluation) -> bool:
    if evaluation is None:
        return False
    if evaluation.severity not in (Severity.MEDIUM, Severity.HIGH):
        return False
    return any(getattr(evaluation, flag) for flag in HARD_FALLBACK_FLAGS)


def run_pipeline(
    request: EvaluateRequest,
    expected_risk_tier: str | None = None,
    expected_guardrail_trigger: bool | None = None,
) -> EvaluationResult:
    settings = get_settings()
    start = time.perf_counter()
    session_id = request.session_id or f"anon-{uuid.uuid4().hex[:12]}"
    context_summary = _context_summary(request.context)

    def elapsed_ms() -> int:
        return int((time.perf_counter() - start) * 1000)

    # --- Step 1: classify --------------------------------------------------
    try:
        risk = llm_client.classify_risk(request.question, context_summary, settings.openai_model_name)
    except Exception as exc:  # noqa: BLE001 - demo-scoped: any provider/parsing error -> safe fallback
        return _provider_error_result(
            session_id, request.question, expected_risk_tier, expected_guardrail_trigger,
            elapsed_ms(), error_detail=str(exc),
        )

    # --- Step 2: primary answer -------------------------------------------
    try:
        primary = llm_client.generate_answer(request.question, context_summary, settings.openai_model_name)
    except Exception as exc:  # noqa: BLE001
        return _provider_error_result(
            session_id, request.question, expected_risk_tier, expected_guardrail_trigger,
            elapsed_ms(), error_detail=str(exc), risk=risk,
        )

    # --- Step 3: guardrail evaluation -------------------------------------
    try:
        guardrail = llm_client.evaluate_guardrails(request.question, primary.answer, settings.guardrail_model)
    except Exception as exc:  # noqa: BLE001
        return _provider_error_result(
            session_id, request.question, expected_risk_tier, expected_guardrail_trigger,
            elapsed_ms(), error_detail=str(exc), risk=risk, raw_answer=primary,
        )

    fallback_guardrail = None

    if not _is_hard_failure(guardrail):
        # Tier 1: clean pass.
        final_action = FinalAction.PASSED
        final_answer = primary.answer
        final_provider = primary.provider_model
    else:
        # Tier 2: attempt one more, stricter generation -- optionally
        # against a different provider/model (literal cross-provider
        # fallback when FALLBACK_MODEL_NAME points at a different vendor
        # via an OpenAI-compatible gateway).
        try:
            fallback = llm_client.generate_answer(
                request.question, context_summary, settings.fallback_model, strict=True
            )
            fallback_guardrail = llm_client.evaluate_guardrails(
                request.question, fallback.answer, settings.guardrail_model
            )
            if _is_hard_failure(fallback_guardrail):
                final_action = FinalAction.SAFE_TEMPLATE
                final_answer = SAFE_TEMPLATE_ANSWER
                final_provider = "safe_template"
            else:
                final_action = FinalAction.PROVIDER_FALLBACK_PASSED
                final_answer = fallback.answer
                final_provider = fallback.provider_model
        except Exception:  # noqa: BLE001 - fallback attempt itself failed -> safest possible outcome
            final_action = FinalAction.SAFE_TEMPLATE
            final_answer = SAFE_TEMPLATE_ANSWER
            final_provider = "safe_template"

    return EvaluationResult(
        session_id=session_id,
        question=request.question,
        risk_classification=risk,
        raw_primary_answer=primary.answer,
        raw_provider_model=primary.provider_model,
        guardrail_evaluation=guardrail,
        fallback_guardrail_evaluation=fallback_guardrail,
        final_action=final_action,
        final_answer=final_answer,
        final_provider_model=final_provider,
        latency_ms=elapsed_ms(),
        expected_risk_tier=expected_risk_tier,
        expected_guardrail_trigger=expected_guardrail_trigger,
    )


def _provider_error_result(
    session_id: str,
    question: str,
    expected_risk_tier: str | None,
    expected_guardrail_trigger: bool | None,
    latency_ms: int,
    error_detail: str,
    risk: RiskClassification | None = None,
    raw_answer=None,
) -> EvaluationResult:
    fallback_risk = risk or RiskClassification(
        category=RiskCategory.LOW_CONTEXT, confidence=0.0, reasoning="unavailable due to a provider/parsing error"
    )
    return EvaluationResult(
        session_id=session_id,
        question=question,
        risk_classification=fallback_risk,
        raw_primary_answer=raw_answer.answer if raw_answer else "",
        raw_provider_model=raw_answer.provider_model if raw_answer else "n/a",
        guardrail_evaluation=None,
        fallback_guardrail_evaluation=None,
        final_action=FinalAction.PROVIDER_ERROR,
        final_answer=SAFE_TEMPLATE_ANSWER,
        final_provider_model="safe_template",
        latency_ms=latency_ms,
        expected_risk_tier=expected_risk_tier,
        expected_guardrail_trigger=expected_guardrail_trigger,
        error_detail=error_detail[:300],
    )
