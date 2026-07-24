"""Auth extensions: email verification, password reset, change password, Google OAuth."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr

from email_service import send_email, verification_email, password_reset_email
from rate_limit import check_rate

logger = logging.getLogger(__name__)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def _jwt_secret():
    return os.environ["JWT_SECRET"]


def _app_url():
    return os.environ.get("APP_PUBLIC_URL", "").rstrip("/")


def create_purpose_token(user_id: str, purpose: str, ttl_hours: int) -> str:
    payload = {
        "sub": user_id,
        "purpose": purpose,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_purpose_token(token: str, expected_purpose: str) -> str:
    payload = None
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "Link has expired")
    except jwt.PyJWTError:
        raise HTTPException(400, "Invalid token")
    if not payload or payload.get("purpose") != expected_purpose:
        raise HTTPException(400, "Invalid token purpose")
    return payload["sub"]


def create_session_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=30)}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


# ---------- Models ----------
class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerifyRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    name: str


class GoogleSessionRequest(BaseModel):
    session_id: str


# ---------- Helpers ----------
async def _send_verification(user: dict):
    token = create_purpose_token(user["id"], "verify_email", 24)
    link = f"{_app_url()}/verify-email?token={token}"
    subject, html = verification_email(user.get("name") or user["email"], link)
    await send_email(user["email"], subject, html)


def build_router(db, current_user):
    router = APIRouter(prefix="/api/auth", tags=["auth-ext"])

    # ----- Email verification -----
    @router.post("/send-verification")
    async def send_verification_authed(user=Depends(current_user)):
        full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
        if full.get("email_verified"):
            return {"ok": True, "already_verified": True}
        await _send_verification(full)
        return {"ok": True}

    @router.post("/resend-verification")
    async def resend_verification(req: ResendVerifyRequest):
        user = await db.users.find_one({"email": req.email.lower()}, {"_id": 0})
        if user and not user.get("email_verified"):
            await _send_verification(user)
        # Always success (no enumeration)
        return {"ok": True}

    @router.post("/verify-email")
    async def verify_email(req: VerifyEmailRequest):
        user_id = decode_purpose_token(req.token, "verify_email")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(404, "User not found")
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"email_verified": True, "verified_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True, "email": user["email"]}

    # ----- Password reset -----
    @router.post("/forgot-password")
    async def forgot_password(req: ForgotPasswordRequest, request: Request):
        check_rate(request, "forgot", max_hits=3, window_seconds=3600)
        user = await db.users.find_one({"email": req.email.lower()}, {"_id": 0})
        if user and user.get("password_hash"):
            token = create_purpose_token(user["id"], "reset_password", 1)
            link = f"{_app_url()}/reset-password?token={token}"
            subject, html = password_reset_email(user.get("name") or user["email"], link)
            await send_email(user["email"], subject, html)
        return {"ok": True}

    @router.post("/reset-password")
    async def reset_password(req: ResetPasswordRequest):
        user_id = decode_purpose_token(req.token, "reset_password")
        if len(req.new_password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(404, "User not found")
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": hash_password(req.new_password),
                      "password_updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True}

    # ----- Change password (authenticated) -----
    @router.post("/change-password")
    async def change_password(req: ChangePasswordRequest, user=Depends(current_user)):
        if len(req.new_password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        full = await db.users.find_one({"id": user["id"]})
        if not full or not full.get("password_hash"):
            raise HTTPException(400, "This account has no password set (Google login?). Use Google to sign in.")
        if not verify_password(req.current_password, full["password_hash"]):
            raise HTTPException(400, "Current password is incorrect")
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"password_hash": hash_password(req.new_password),
                      "password_updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"ok": True}

    # ----- Update profile -----
    @router.post("/update-profile")
    async def update_profile(req: UpdateProfileRequest, user=Depends(current_user)):
        name = req.name.strip()
        if not name:
            raise HTTPException(400, "Name is required")
        await db.users.update_one({"id": user["id"]}, {"$set": {"name": name}})
        return {"ok": True, "name": name}

    # ----- Google OAuth (Emergent-managed) -----
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    @router.post("/google/session")
    async def google_session(req: GoogleSessionRequest):
        # Exchange session_id for user profile via Emergent Auth
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                r = await http.get(
                    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                    headers={"X-Session-ID": req.session_id},
                )
                if r.status_code != 200:
                    raise HTTPException(401, "Invalid Google session")
                data = r.json()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Emergent auth error: {e}")
            raise HTTPException(500, f"Google auth failed: {e}")

        email = (data.get("email") or "").lower()
        if not email:
            raise HTTPException(400, "Google returned no email")

        # Find or create user
        existing = await db.users.find_one({"email": email})
        now = datetime.now(timezone.utc).isoformat()
        if existing:
            update = {"google_id": data.get("id"), "picture": data.get("picture"),
                      "email_verified": True, "last_login_at": now}
            if not existing.get("name") and data.get("name"):
                update["name"] = data.get("name")
            await db.users.update_one({"id": existing["id"]}, {"$set": update})
            user_id = existing["id"]
            user_name = existing.get("name") or data.get("name") or email.split("@")[0]
        else:
            user_id = str(uuid.uuid4())
            await db.users.insert_one({
                "id": user_id,
                "email": email,
                "name": data.get("name") or email.split("@")[0],
                "picture": data.get("picture"),
                "google_id": data.get("id"),
                "email_verified": True,  # Google emails are verified
                "auth_provider": "google",
                "created_at": now,
            })
            user_name = data.get("name") or email.split("@")[0]

        token = create_session_token(user_id)
        return {
            "token": token,
            "user": {"id": user_id, "email": email, "name": user_name, "picture": data.get("picture")},
        }

    return router
