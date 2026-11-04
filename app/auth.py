import hmac
import hashlib
import os
import time
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

# Configurable credentials from environment
SMM_AUTH_USER = os.getenv("SMM_AUTH_USER", "admin")
SMM_AUTH_PASS = os.getenv("SMM_AUTH_PASS", "SeeMyMind2026!")

HALO_AUTH_USER = os.getenv("HALO_AUTH_USER", "halo")
HALO_AUTH_PASS = os.getenv("HALO_AUTH_PASS", "HaloLeads2026!")

SESSION_SECRET = os.getenv("SESSION_SECRET", "leadgen-suite-secret-key-salt-98124").encode("utf-8")
SESSION_MAX_AGE_DAYS = 14
SESSION_MAX_AGE_SECONDS = SESSION_MAX_AGE_DAYS * 24 * 3600


def create_token(role: str) -> str:
    """Generate a signed, timestamped session token."""
    ts = str(int(time.time()))
    payload = f"{role}:{ts}"
    signature = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_token(token: Optional[str], expected_role: str) -> bool:
    """Verify that the token signature matches and has not expired."""
    if not token:
        return False
    parts = token.split(":")
    if len(parts) != 3:
        return False
    role, ts_str, signature = parts
    if role != expected_role:
        return False
    try:
        ts = int(ts_str)
        # Check expiration (14 days)
        if time.time() - ts > SESSION_MAX_AGE_SECONDS:
            return False
    except ValueError:
        return False

    payload = f"{role}:{ts_str}"
    expected_sig = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected_sig)


def is_smm_authenticated(request: Request) -> bool:
    token = request.cookies.get("smm_session")
    return verify_token(token, "smm")


def is_halo_authenticated(request: Request) -> bool:
    token = request.cookies.get("halo_session")
    return verify_token(token, "halo")
