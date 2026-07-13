"""Import all ORM models here so Alembic autogenerate and metadata see them.

Add new module models to this file as the project grows.
"""

from app.core.database import Base
from app.modules.analytics.models import DailyStat
from app.modules.auth.models import AuthCredential, RefreshToken, User
from app.modules.campus.models import Campus
from app.modules.errands.models import (
    Errand,
    ErrandEvent,
    ErrandHandoffSecret,
    ErrandItem,
    Rating,
)
from app.modules.ledger.models import LedgerEntry
from app.modules.notifications.models import Notification
from app.modules.outbox.models import OutboxEvent, ProcessedEvent
from app.modules.runners.models import RunnerProfile
from app.modules.timetable.models import TimetableSlot
from app.modules.vendors.models import MenuItem, Vendor

__all__ = [
    "Base",
    "Campus",
    "User",
    "AuthCredential",
    "RefreshToken",
    "Errand",
    "ErrandEvent",
    "ErrandHandoffSecret",
    "RunnerProfile",
    "OutboxEvent",
    "ProcessedEvent",
    "Notification",
    "DailyStat",
    "TimetableSlot",
    "ErrandItem",
    "Rating",
    "LedgerEntry",
    "Vendor",
    "MenuItem",
]
