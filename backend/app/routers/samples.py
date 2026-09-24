from fastapi import APIRouter

from ..sample_data import SAMPLE_QUESTIONS

router = APIRouter()


@router.get("/samples")
def list_samples() -> list[dict]:
    """The curated question set used by the demo picker and the batch run."""
    return SAMPLE_QUESTIONS
