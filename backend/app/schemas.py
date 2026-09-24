"""
Typed schemas for GuardedContext.

Every AI call in this project returns one of these typed models rather
than free-form text, mirroring the "typed schemas" pattern described in
the target job posting (PydanticAI-style structured agent outputs).
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class RiskCategory(str, Enum):
    LOW_CONTEXT = "low_context"
    SYMPTOM_EXPLANATION = "symptom_explanation"
    URGENCY_ADJACENT = "urgency_adjacent"
    MEDICATION_RELATED = "medication_related"


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FinalAction(str, Enum):
    PASSED = "passed"
    PROVIDER_FALLBACK_PASSED = "provider_fallback_passed"
    SAFE_TEMPLATE = "safe_template"
    PROVIDER_ERROR = "provider_error"


class UserContext(BaseModel):
    cycle_phase: Optional[str] = None
    recent_symptoms: Optional[str] = None
    sleep_summary: Optional[str] = None


class EvaluateRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    context: Optional[UserContext] = None
    session_id: Optional[str] = None


class RiskClassification(BaseModel):
    category: RiskCategory
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PrimaryAnswer(BaseModel):
    answer: str
    provider_model: str


class GuardrailEvaluation(BaseModel):
    missed_urgency: bool
    inappropriate_recommendation: bool
    incorrect_treatment_advice: bool
    missing_critical_info: bool
    severity: Severity
    rationale: str

    @property
    def any_flag(self) -> bool:
        return any(
            [
                self.missed_urgency,
                self.inappropriate_recommendation,
                self.incorrect_treatment_advice,
                self.missing_critical_info,
            ]
        )


class EvaluationResult(BaseModel):
    session_id: str
    question: str
    risk_classification: RiskClassification
    raw_primary_answer: str
    raw_provider_model: str
    guardrail_evaluation: Optional[GuardrailEvaluation] = None
    fallback_guardrail_evaluation: Optional[GuardrailEvaluation] = None
    final_action: FinalAction
    final_answer: str
    final_provider_model: str
    latency_ms: int
    expected_risk_tier: Optional[str] = None
    expected_guardrail_trigger: Optional[bool] = None
    error_detail: Optional[str] = None


class SampleQuestion(BaseModel):
    id: str
    question: str
    expected_risk_tier: RiskCategory
    expected_guardrail_trigger: bool


class HistoryEntry(BaseModel):
    id: int
    timestamp: datetime
    session_id: str
    question: str
    risk_category: str
    final_action: str
    final_provider_model: str
    any_flag: bool
    severity: str
    expected_risk_tier: Optional[str] = None
    expected_guardrail_trigger: Optional[bool] = None


class BatchSummary(BaseModel):
    total: int
    passed_clean: int
    guardrail_triggered: int
    provider_fallback_used: int
    provider_errors: int
    accuracy_vs_expected: float
    by_category: Dict[str, int]
