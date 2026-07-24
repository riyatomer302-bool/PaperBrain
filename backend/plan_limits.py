"""Plan enforcement helpers - per-user limits for Free tier."""
from datetime import datetime, timezone
from fastapi import HTTPException

FREE_LIMITS = {"documents": 10, "chunks": 200, "chats_per_month": 50}


async def get_active_plan(db, user_id: str) -> str:
    sub = await db.subscriptions.find_one(
        {"user_id": user_id, "status": "active"}, {"_id": 0}
    )
    if not sub:
        return "free"
    expires_at = sub.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        await db.subscriptions.update_one({"id": sub["id"]}, {"$set": {"status": "expired"}})
        return "free"
    return sub.get("plan_id", "pro")


def _month_start_iso():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


async def get_usage(db, user_id: str) -> dict:
    docs_count = await db.documents.count_documents({"user_id": user_id})
    agg = await db.documents.aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": None, "chunks": {"$sum": "$chunk_count"}}},
    ]).to_list(1)
    chunks_used = int(agg[0]["chunks"]) if agg else 0
    month_start = _month_start_iso()
    # Prefer direct user_id filter on messages (added later). Fall back to
    # conversation_id lookup for messages inserted before user_id was tracked.
    chats_direct = await db.messages.count_documents({
        "user_id": user_id,
        "role": "user",
        "created_at": {"$gte": month_start},
    })
    if chats_direct == 0:
        # Legacy path — messages without user_id
        chats_direct = await db.messages.count_documents({
            "role": "user",
            "created_at": {"$gte": month_start},
            "conversation_id": {"$in": await _user_conversation_ids(db, user_id)},
        })
    return {
        "documents": docs_count,
        "chunks": chunks_used,
        "chats_this_month": chats_direct,
        "month_started_at": month_start,
    }


async def _user_conversation_ids(db, user_id: str) -> list:
    ids = await db.conversations.find(
        {"user_id": user_id}, {"_id": 0, "id": 1}
    ).to_list(1000)
    return [c["id"] for c in ids]


async def enforce_document_limit(db, user_id: str, plan: str, additional_chunks: int = 0):
    if plan != "free":
        return
    usage = await get_usage(db, user_id)
    if usage["documents"] >= FREE_LIMITS["documents"]:
        raise HTTPException(
            402,
            f"Free plan limit reached: {FREE_LIMITS['documents']} documents. Upgrade to Pro for unlimited.",
        )
    if additional_chunks and (usage["chunks"] + additional_chunks) > FREE_LIMITS["chunks"]:
        raise HTTPException(
            402,
            f"Free plan chunk limit ({FREE_LIMITS['chunks']}) would be exceeded. Upgrade to Pro for unlimited.",
        )


async def enforce_chat_limit(db, user_id: str, plan: str):
    if plan != "free":
        return
    usage = await get_usage(db, user_id)
    if usage["chats_this_month"] >= FREE_LIMITS["chats_per_month"]:
        raise HTTPException(
            402,
            f"Free plan limit reached: {FREE_LIMITS['chats_per_month']} chats this month. Upgrade to Pro for unlimited.",
        )


async def enforce_chunk_post_index(db, user_id: str, plan: str, current_chunks_added: int):
    """Called AFTER document is chunked but BEFORE saving to Chroma (or as a rollback check).
       Simpler alternative: rollback in caller if over limit."""
    if plan != "free":
        return
    usage = await get_usage(db, user_id)
    if usage["chunks"] + current_chunks_added > FREE_LIMITS["chunks"]:
        raise HTTPException(
            402,
            f"This document would exceed the Free plan chunk limit ({FREE_LIMITS['chunks']}). Upgrade to Pro for unlimited.",
        )
