import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mongo import chat_messages
from app.core.redis import redis_client
from app.modules.auth.models import User
from app.modules.errands.service import STATUS_CHANNEL_PREFIX, ErrandError, get_errand

CHAT_HISTORY_LIMIT = 100


async def _authorized_errand(db: AsyncSession, user: User, errand_id: uuid.UUID):
    """Chat is between the two parties of an errand, and only once a runner
    is assigned (there's nobody to talk to before that)."""
    errand = await get_errand(db, user, errand_id)  # 404s if wrong campus / missing
    if errand.runner_id is None:
        raise ErrandError("Chat opens once a runner accepts the errand.", 409)
    if user.id not in (errand.requester_id, errand.runner_id):
        raise ErrandError("Only the requester and runner can chat here.", 403)
    return errand


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "errand_id": doc["errand_id"],
        "sender_id": doc["sender_id"],
        "sender_name": doc["sender_name"],
        "body": doc["body"],
        "created_at": doc["created_at"],
    }


async def list_messages(db: AsyncSession, user: User, errand_id: uuid.UUID) -> list[dict]:
    await _authorized_errand(db, user, errand_id)
    cursor = (
        chat_messages.find({"errand_id": str(errand_id)})
        .sort("created_at", 1)
        .limit(CHAT_HISTORY_LIMIT)
    )
    return [_serialize(doc) async for doc in cursor]


async def send_message(
    db: AsyncSession, user: User, errand_id: uuid.UUID, body: str
) -> dict:
    await _authorized_errand(db, user, errand_id)
    doc = {
        "errand_id": str(errand_id),
        "sender_id": str(user.id),
        "sender_name": user.display_name,
        "body": body,
        "created_at": datetime.now(UTC).isoformat(),
    }
    result = await chat_messages.insert_one(doc)
    doc["_id"] = result.inserted_id
    message = _serialize(doc)
    # Live delivery: reuse the errand's WS channel — the other party's
    # tracking page is already subscribed to it.
    await redis_client.publish(
        f"{STATUS_CHANNEL_PREFIX}{errand_id}",
        json.dumps({"type": "chat", **message}),
    )
    return message
