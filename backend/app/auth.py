"""
Optional shared-passcode gate.

This is NOT a real auth system -- it exists purely so a publicly deployed
demo can't be used by strangers to run up API costs. If DEMO_ACCESS_CODE
is unset (the default for local development), every request passes.
"""
from typing import Optional

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_demo_access(x_demo_code: Optional[str] = Header(default=None)) -> bool:
    settings = get_settings()
    if not settings.demo_access_code:
        return True
    if x_demo_code != settings.demo_access_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or incorrect demo access code (X-Demo-Code header).",
        )
    return True
