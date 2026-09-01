"""Delivery to Expo's push service.

The WebSocket fan-out only reaches a user whose app is open. This is the other
half: an OS-level banner that arrives whether or not the app is running.

Kept deliberately small and best-effort — a push that fails must never take
down the consumer that was writing a ledger entry or a notification row. The
notification is already durable in Postgres by the time we get here; the push
is a nicety on top.
"""

import logging
from typing import Any

import httpx

from app.core.resilience import CircuitBreaker, CircuitOpenError

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Expo accepts up to 100 messages per request.
BATCH_SIZE = 100
TIMEOUT_SECONDS = 10

# Same reasoning as the Kafka producer: if Expo is down, stop hammering it.
_breaker = CircuitBreaker("expo-push", failure_threshold=5, reset_timeout=30)


def _looks_like_expo_token(token: str) -> bool:
    return token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")


async def send_push(
    tokens: list[str],
    title: str,
    body: str | None = None,
    data: dict[str, Any] | None = None,
) -> list[str]:
    """Push to every token. Returns the tokens Expo rejected as unregistered.

    Callers should delete returned tokens — they belong to uninstalled apps and
    will never deliver again.
    """
    valid = [t for t in tokens if _looks_like_expo_token(t)]
    if not valid:
        return []

    dead: list[str] = []

    for start in range(0, len(valid), BATCH_SIZE):
        chunk = valid[start : start + BATCH_SIZE]
        messages = [
            {
                "to": token,
                "title": title,
                "body": body or "",
                "data": data or {},
                "sound": "default",
                # Android needs a channel for the banner to show while the app
                # is backgrounded; the client creates one with this id.
                "channelId": "default",
            }
            for token in chunk
        ]

        try:
            payload = await _breaker.call(lambda m=messages: _post(m))
        except CircuitOpenError:
            logger.warning("expo push breaker open — skipping %d message(s)", len(chunk))
            continue
        except Exception:
            logger.exception("expo push failed for %d message(s)", len(chunk))
            continue

        # Expo replies per-message, in request order.
        for token, result in zip(chunk, payload.get("data", []), strict=False):
            if result.get("status") == "ok":
                continue
            err = (result.get("details") or {}).get("error")
            if err == "DeviceNotRegistered":
                dead.append(token)
            else:
                logger.warning("expo push rejected %s: %s", token[:24], result.get("message"))

    return dead


async def _post(messages: list[dict[str, Any]]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        res = await client.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={"accept": "application/json", "content-type": "application/json"},
        )
        res.raise_for_status()
        return res.json()
