"""Payment provider port (hexagonal boundary).

Wallet top-ups and refunds go through this interface so the escrow/ledger core
never depends on a concrete gateway. Today a SimulatedProvider settles
instantly (KARMA credits); a real UPI/Razorpay provider implements the same
two methods later — and nothing in service.py changes. Real gateways bring
API keys, webhooks and KYC, which are configured out-of-band, never here.
"""

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass
class TopupResult:
    ok: bool
    provider_ref: str
    message: str = ""


class PaymentProvider(Protocol):
    name: str

    async def create_topup(self, user_id: str, amount: float) -> TopupResult: ...

    async def refund(self, provider_ref: str, amount: float) -> TopupResult: ...


class SimulatedProvider:
    """Instant, always-succeeds top-ups for dev/demo. No real money moves."""

    name = "simulated"

    async def create_topup(self, user_id: str, amount: float) -> TopupResult:
        return TopupResult(ok=True, provider_ref=f"sim-{user_id[:8]}-{int(amount * 100)}")

    async def refund(self, provider_ref: str, amount: float) -> TopupResult:
        return TopupResult(ok=True, provider_ref=f"sim-refund-{provider_ref}")


_PROVIDERS: dict[str, PaymentProvider] = {"simulated": SimulatedProvider()}


def get_provider() -> PaymentProvider:
    return _PROVIDERS.get(settings.payment_provider, _PROVIDERS["simulated"])
