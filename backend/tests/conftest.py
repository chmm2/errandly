import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.main import app
from app.modules.campus.models import Campus


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def campus():
    """Ensure a default campus exists for registration."""
    async with SessionLocal() as db:
        c = await db.scalar(select(Campus).limit(1))
        if c is None:
            c = Campus(name="Test Campus")
            db.add(c)
            await db.commit()
            await db.refresh(c)
        return c.id
