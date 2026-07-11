"""WebSocket endpoints — async request-reply over Redis pub/sub.

The HTTP side publishes (errand status changes, runner offers) and these
sockets subscribe and forward. Any API replica can serve any socket because
the fan-out lives in Redis, not in process memory — statelessness holds.
"""

import asyncio
import contextlib
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.redis import redis_client
from app.core.security import decode_token
from app.modules.errands.service import OFFER_CHANNEL_PREFIX, STATUS_CHANNEL_PREFIX

router = APIRouter()


def _user_id_from_token(token: str) -> uuid.UUID | None:
    """WebSockets can't send Authorization headers from browsers — the
    access token arrives as a query parameter instead."""
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return uuid.UUID(payload["sub"])


async def _forward_channel(websocket: WebSocket, channel: str) -> None:
    """Subscribe to one Redis channel and forward every message to the socket."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
            if message is not None:
                await websocket.send_text(message["data"])
            else:
                # Heartbeat keeps intermediaries from closing the idle socket.
                await websocket.send_text('{"type":"ping"}')
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


@router.websocket("/ws/errands/{errand_id}")
async def errand_status_socket(websocket: WebSocket, errand_id: uuid.UUID, token: str = ""):
    """Live order tracking: push every status transition of one errand."""
    if _user_id_from_token(token) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    forward = asyncio.create_task(
        _forward_channel(websocket, f"{STATUS_CHANNEL_PREFIX}{errand_id}")
    )
    try:
        while True:  # drain client frames so disconnects surface
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        forward.cancel()


@router.websocket("/ws/runner")
async def runner_offer_socket(websocket: WebSocket, token: str = ""):
    """Offer push: matching publishes to the runner's personal channel."""
    user_id = _user_id_from_token(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    forward = asyncio.create_task(
        _forward_channel(websocket, f"{OFFER_CHANNEL_PREFIX}{user_id}")
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        forward.cancel()
