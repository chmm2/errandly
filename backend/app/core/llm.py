"""One way to ask a language model for a schema-shaped answer.

Two providers behind one function, chosen by configuration:

  * **ollama** - a model running on campus hardware. Nothing a student wrote
    leaves the building, which for a system whose evidence is errand notes and
    reviews about identifiable people is a real property and not a fallback.
  * **anthropic** - a hosted frontier model, better at the nuanced calls, kept
    as the reference implementation to measure the local one against.

Both return a validated Pydantic instance or **None**. None is the contract:
every caller in `modules/fraud` treats it as "no opinion" and changes nothing,
so an unreachable model, a refusal, a timeout or a garbled answer all degrade
to the behaviour the system had before any model existed. That is why the
provider can be swapped without touching a single fraud rule.

Both are constrained to a schema rather than asked politely for JSON. Ollama
constrains generation at the token level against the schema, so malformed JSON
is mechanically impossible; Anthropic validates server-side. Neither leaves the
shape of the answer to chance, which matters here because the text being
analysed is written by the people under investigation - the worst a crafted
note can achieve is a wrong number inside a valid schema, never a free-form
response that becomes an instruction.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ANTHROPIC_MODEL = "claude-opus-5"

# Deterministic on purpose. Two admins looking at the same flag should see the
# same reading, and a fraud judgement that changes between refreshes is not
# evidence of anything.
OLLAMA_TEMPERATURE = 0.0
OLLAMA_TIMEOUT_S = 180.0


def provider() -> str:
    """Which provider is configured, or "none"."""
    name = (getattr(settings, "llm_provider", "") or "").strip().lower()
    if name == "ollama":
        return "ollama"
    if name == "anthropic" and getattr(settings, "anthropic_api_key", ""):
        return "anthropic"
    # Unset but a key is present: assume the hosted provider was intended.
    if not name and getattr(settings, "anthropic_api_key", ""):
        return "anthropic"
    return "none"


def model_name() -> str:
    p = provider()
    if p == "ollama":
        return getattr(settings, "ollama_model", "")
    if p == "anthropic":
        return ANTHROPIC_MODEL
    return ""


def configured() -> bool:
    return provider() != "none"



def _describe_schema(output_model: type[T]) -> str:
    """Restate the schema's field guidance as plain text, for Ollama.

    Anthropic is handed the schema and reads the descriptions off it. Ollama
    uses the schema as a DECODING GRAMMAR: it constrains the shape of the
    answer and nothing else, so descriptions and numeric bounds never reach
    the model at all.

    That is not a theoretical gap. Asked for a 0-100 score with the range
    stated only in the field description, a 7B model answered 4 and 5 - a
    five-point scale it invented - and Pydantic then rejected every reply, so
    the whole channel returned "no opinion" for a reason nobody could see.
    With the same guidance restated in the prompt, the same model scored 95
    against 20 on the same pair. The descriptions are the instructions; they
    have to be in the conversation, not only in the grammar.
    """
    schema = output_model.model_json_schema()
    lines: list[str] = []
    for name, spec in (schema.get("properties") or {}).items():
        kind = spec.get("type", "value")
        bounds = ""
        if "minimum" in spec and "maximum" in spec:
            bounds = f", {spec['minimum']} to {spec['maximum']}"
        desc = spec.get("description", "").strip()
        lines.append(f"- {name} ({kind}{bounds}): {desc}")
    if not lines:
        return ""
    return (
        "Answer with exactly these fields, and respect every stated range:\n"
        + "\n".join(lines)
    )


async def _ollama(
    output_model: type[T], *, system: str, prompt: str, max_tokens: int
) -> T | None:
    url = getattr(settings, "ollama_url", "").rstrip("/")
    model = getattr(settings, "ollama_model", "")
    if not url or not model:
        return None

    guidance = _describe_schema(output_model)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system + ("\n\n" + guidance if guidance else ""),
            },
            {"role": "user", "content": prompt},
        ],
        # The schema itself, not a request for JSON. Generation is constrained
        # to tokens the schema admits, so the reply cannot be prose.
        "format": output_model.model_json_schema(),
        "stream": False,
        "options": {"temperature": OLLAMA_TEMPERATURE, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_S) as client:
        response = await client.post(f"{url}/api/chat", json=payload)
        response.raise_for_status()
        content = (response.json().get("message") or {}).get("content") or ""

    # Constrained decoding makes this parse in practice; it is still guarded,
    # because a truncated generation produces valid-prefix-invalid-whole JSON
    # and a fraud channel must not raise on a bad answer.
    return output_model.model_validate(json.loads(content))


async def _anthropic(
    output_model: type[T], *, system: str, prompt: str, max_tokens: int
) -> T | None:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.parse(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_model,
        )
    finally:
        await client.close()

    if getattr(response, "stop_reason", None) == "refusal":
        logger.info("model declined the request; recording no opinion")
        return None
    return getattr(response, "parsed_output", None)


async def structured(
    output_model: type[T], *, system: str, prompt: str, max_tokens: int = 8000
) -> T | None:
    """Ask the configured model for one schema-shaped answer.

    Returns None on every failure path - no provider, unreachable server,
    timeout, refusal, malformed answer. Callers must treat None as "no
    opinion", never as a negative finding.
    """
    p = provider()
    if p == "none":
        return None

    try:
        if p == "ollama":
            return await _ollama(
                output_model, system=system, prompt=prompt, max_tokens=max_tokens
            )
        return await _anthropic(
            output_model, system=system, prompt=prompt, max_tokens=max_tokens
        )
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError):
        logger.warning("%s returned nothing usable; proceeding without it", p, exc_info=True)
        return None
    except ImportError:
        logger.warning("provider %s is configured but its SDK is not installed", p)
        return None
    except Exception:
        logger.warning("%s call failed; proceeding without it", p, exc_info=True)
        return None
