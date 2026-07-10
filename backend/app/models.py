"""Import all ORM models here so Alembic autogenerate and metadata see them.

Add new module models to this file as the project grows.
"""

from app.core.database import Base
from app.modules.auth.models import AuthCredential, RefreshToken, User
from app.modules.campus.models import Campus
from app.modules.errands.models import Errand, ErrandEvent

__all__ = [
    "Base",
    "Campus",
    "User",
    "AuthCredential",
    "RefreshToken",
    "Errand",
    "ErrandEvent",
]
