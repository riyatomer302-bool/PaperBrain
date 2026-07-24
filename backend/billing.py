"""Razorpay billing module for subscription management."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Plans configuration (INR paise)
PRO_AMOUNT_INR = int(os.environ.get("PRO_PLAN_AMOUNT_INR", "499"))
PRO_AMOUNT_PAISE = PRO_AMOUNT_INR * 100

PLANS = {
    "free": {
        "id": "free",
        "name": "Free",
        "price_inr": 0,
        "period": "forever",
        "features": [
            "10 documents",
            "200 vector chunks",
            "50 chat messages / month",
            "Local vector storage",
            "Community support",
        ],
        "limits": {"documents": 10, "chunks": 200, "chats_per_month": 50},
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price_inr": PRO_AMOUNT_INR,
        "period": "month",
        "features": [
            "Unlimited documents",
            "Unlimited vector chunks",
            "Unlimited chat messages",
            "URL & email ingestion",
            "Priority Claude Sonnet 4.5",
            "Priority support",
        ],
        "limits": {"documents": None, "chunks": None, "chats_per_month": None},
    },
}

RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RZP_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")


def _get_client():
    kid = os.environ.get("RAZORPAY_KEY_ID", "")
    ksec = os.environ.get("RAZORPAY_KEY_SECRET", "")
    if not kid or not ksec:
        return None
    return razorpay.Client(auth=(kid, ksec))


rzp_client = _get_client()


class CreateOrderRequest(BaseModel):
    plan_id: str  # "pro"


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    payment_record_id: str


def build_router(db, current_user):
    router = APIRouter(prefix="/api/billing", tags=["billing"])

    @router.get("/payments")
    async def payments_history(user=Depends(current_user)):
        rows = await db.payments.find(
            {"user_id": user["id"]},
            {"_id": 0, "razorpay_signature": 0},
        ).sort("created_at", -1).to_list(200)
        # Attach plan name and paise->rupees
        for r in rows:
            r["plan_name"] = PLANS.get(r.get("plan_id", "free"), {}).get("name", r.get("plan_id"))
            r["amount_inr"] = round((r.get("amount") or 0) / 100, 2)
        return {"payments": rows}

    @router.get("/plans")
    async def list_plans():
        return {"plans": list(PLANS.values()), "currency": "INR", "razorpay_key_id": os.environ.get("RAZORPAY_KEY_ID", "")}

    @router.get("/status")
    async def subscription_status(user=Depends(current_user)):
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "status": "active"}, {"_id": 0}
        )
        if sub:
            # Check expiry
            expires_at = sub.get("expires_at")
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                await db.subscriptions.update_one(
                    {"id": sub["id"]}, {"$set": {"status": "expired"}}
                )
                sub = None
        return {
            "plan": sub["plan_id"] if sub else "free",
            "status": "active" if sub else "free",
            "expires_at": sub.get("expires_at") if sub else None,
            "plan_details": PLANS[sub["plan_id"] if sub else "free"],
        }

    @router.get("/usage")
    async def usage(user=Depends(current_user)):
        from plan_limits import get_active_plan, get_usage, FREE_LIMITS
        plan = await get_active_plan(db, user["id"])
        u = await get_usage(db, user["id"])
        limits = PLANS[plan]["limits"]
        def pct(used, cap):
            if cap is None or cap == 0:
                return 0
            return min(100, round((used / cap) * 100))
        return {
            "plan": plan,
            "usage": u,
            "limits": limits,
            "percent": {
                "documents": pct(u["documents"], limits.get("documents")),
                "chunks": pct(u["chunks"], limits.get("chunks")),
                "chats": pct(u["chats_this_month"], limits.get("chats_per_month")),
            },
            "free_limits": FREE_LIMITS,
        }

    @router.post("/create-order")
    async def create_order(req: CreateOrderRequest, user=Depends(current_user)):
        if req.plan_id not in PLANS or req.plan_id == "free":
            raise HTTPException(400, "Invalid plan")
        client = _get_client()
        if not client:
            raise HTTPException(500, "Razorpay not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to backend/.env")

        plan = PLANS[req.plan_id]
        amount_paise = plan["price_inr"] * 100
        receipt = f"pro-{user['id'][:8]}-{int(datetime.now(timezone.utc).timestamp())}"
        key_id = os.environ.get("RAZORPAY_KEY_ID", "")

        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt[:40],
                "notes": {"user_id": user["id"], "plan_id": req.plan_id, "email": user["email"]},
            })
        except Exception as e:
            logger.error(f"Razorpay order creation failed: {e}")
            raise HTTPException(500, f"Razorpay error: {e}")
        if not order or "id" not in order:
            raise HTTPException(500, "Razorpay did not return a valid order")

        payment_record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.payments.insert_one({
            "id": payment_record_id,
            "user_id": user["id"],
            "plan_id": req.plan_id,
            "razorpay_order_id": order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "status": "created",
            "created_at": now,
        })

        return {
            "order_id": order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "key_id": key_id,
            "payment_record_id": payment_record_id,
            "plan_name": plan["name"],
            "prefill": {"email": user["email"], "name": user.get("name", "")},
        }

    @router.post("/verify-payment")
    async def verify_payment(req: VerifyPaymentRequest, user=Depends(current_user)):
        client = _get_client()
        if not client:
            raise HTTPException(500, "Razorpay not configured")

        payment_rec = await db.payments.find_one(
            {"id": req.payment_record_id, "user_id": user["id"]}
        )
        if not payment_rec:
            raise HTTPException(404, "Payment record not found")

        # Verify signature
        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": req.razorpay_order_id,
                "razorpay_payment_id": req.razorpay_payment_id,
                "razorpay_signature": req.razorpay_signature,
            })
        except Exception as e:
            await db.payments.update_one(
                {"id": req.payment_record_id},
                {"$set": {"status": "signature_failed", "error": str(e)}},
            )
            raise HTTPException(400, f"Invalid payment signature: {e}")

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)

        await db.payments.update_one(
            {"id": req.payment_record_id},
            {"$set": {
                "status": "paid",
                "razorpay_payment_id": req.razorpay_payment_id,
                "razorpay_signature": req.razorpay_signature,
                "paid_at": now.isoformat(),
            }},
        )

        # Deactivate any prior active subs
        await db.subscriptions.update_many(
            {"user_id": user["id"], "status": "active"},
            {"$set": {"status": "superseded"}},
        )
        sub_id = str(uuid.uuid4())
        await db.subscriptions.insert_one({
            "id": sub_id,
            "user_id": user["id"],
            "plan_id": payment_rec["plan_id"],
            "status": "active",
            "razorpay_payment_id": req.razorpay_payment_id,
            "razorpay_order_id": req.razorpay_order_id,
            "started_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "amount": payment_rec["amount"],
        })

        return {
            "success": True,
            "plan": payment_rec["plan_id"],
            "expires_at": expires.isoformat(),
        }

    @router.post("/webhook")
    async def webhook(request: Request):
        payload = await request.body()
        signature = request.headers.get("X-Razorpay-Signature", "")
        client = _get_client()
        webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        if not client or not webhook_secret:
            raise HTTPException(500, "Webhook not configured")
        try:
            client.utility.verify_webhook_signature(
                payload.decode(), signature, webhook_secret
            )
        except Exception as e:
            raise HTTPException(400, f"Invalid webhook signature: {e}")
        # Persist raw event for auditing
        import json as _json
        try:
            event = _json.loads(payload)
        except Exception:
            event = {"raw": payload.decode(errors="ignore")}
        await db.webhook_events.insert_one({
            "id": str(uuid.uuid4()),
            "event": event.get("event"),
            "payload": event,
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "ok"}

    return router
