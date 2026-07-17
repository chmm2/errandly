import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import require_active_user
from app.modules.auth.models import User
from app.modules.chat import service
from app.modules.errands.service import ErrandError

router = APIRouter(prefix="/errands", tags=["chat"])


class ChatMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatMessageOut(BaseModel):
    id: str
    errand_id: str
    sender_id: str
    sender_name: str
    body: str
    created_at: str


@router.get("/{errand_id}/chat", response_model=list[ChatMessageOut])
async def history(
    errand_id: uuid.UUID,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.list_messages(db, user, errand_id)
    except ErrandError as e:
        raise HTTPException(e.status_code, e.message) from e


@router.post(
    "/{errand_id}/chat",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send(
    errand_id: uuid.UUID,
    data: ChatMessageIn,
    user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.send_message(db, user, errand_id, data.body)
    except ErrandError as e:
        raise HTTPException(e.status_code, e.message) from e
