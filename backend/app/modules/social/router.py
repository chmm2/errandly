import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.social import service
from app.modules.social.schemas import (
    FriendOut,
    FriendRequestCreate,
    PendingRequestOut,
    RespondRequest,
    SearchResultOut,
)

router = APIRouter(prefix="/social", tags=["social"])


def _wrap(e: service.SocialError) -> HTTPException:
    return HTTPException(e.status_code, e.message)


@router.get("/friends", response_model=list[FriendOut])
async def friends(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.list_friends(db, current_user)


@router.get("/requests", response_model=list[PendingRequestOut])
async def pending_requests(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    rows = await service.list_pending(db, current_user)
    return [
        PendingRequestOut(
            id=row.id, from_user=FriendOut.model_validate(user), created_at=row.created_at
        )
        for row, user in rows
    ]


@router.post("/requests", response_model=dict, status_code=status.HTTP_201_CREATED)
async def send_request(
    data: FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await service.request_friend(db, current_user, data.user_id)
    except service.SocialError as e:
        raise _wrap(e) from e
    return {"id": str(row.id), "status": row.status}


@router.post("/requests/{friendship_id}/respond", response_model=dict)
async def respond(
    friendship_id: uuid.UUID,
    data: RespondRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await service.respond_to_request(db, current_user, friendship_id, data.accept)
    except service.SocialError as e:
        raise _wrap(e) from e
    return {"id": str(row.id), "status": row.status}


@router.delete("/friends/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfriend(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.remove_friend(db, current_user, user_id)
    except service.SocialError as e:
        raise _wrap(e) from e


@router.post("/block/{user_id}", response_model=dict)
async def block(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await service.block_user(db, current_user, user_id)
    except service.SocialError as e:
        raise _wrap(e) from e
    return {"id": str(row.id), "status": row.status}


@router.get("/search", response_model=list[SearchResultOut])
async def search(
    q: str = Query(min_length=2, max_length=64),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.search_students(db, current_user, q)
