"""Notification endpoints: REST feed (list/mark-read) plus a WebSocket for
live push. The WebSocket can't reuse the regular Bearer-auth dependency —
browsers can't set custom headers on a WebSocket handshake — so the access
token travels as a query param instead (`/ws/notifications?token=...`),
validated the same way as app/core/deps.py::get_current_user.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import Message
from app.core.database import AsyncSessionLocal
from app.core.deps import get_current_user, get_db
from app.core.exceptions import NotFoundError
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.notifications import repository
from app.notifications.schemas import NotificationList, NotificationRead
from app.notifications.ws_manager import manager as ws_manager
from app.users.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
async def list_notifications(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> NotificationList:
    items = await repository.list_for_user(db, current_user.id)
    unread_count = await repository.count_unread(db, current_user.id)
    return NotificationList(items=[NotificationRead.model_validate(n) for n in items], unread_count=unread_count)


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationRead:
    notification = await repository.get_by_id(db, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise NotFoundError("Notification introuvable.")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)
    return NotificationRead.model_validate(notification)


@router.post("/read-all", response_model=Message)
async def mark_all_read(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> Message:
    await repository.mark_all_read(db, current_user.id)
    await db.commit()
    return Message(detail="Notifications marquées comme lues.")


@router.delete("/{notification_id}", response_model=Message)
async def delete_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Message:
    notification = await repository.get_by_id(db, notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise NotFoundError("Notification introuvable.")
    await db.delete(notification)
    await db.commit()
    return Message(detail="Notification supprimée.")


@router.delete("", response_model=Message)
async def delete_read_notifications(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Message:
    """Vide les notifications déjà lues (les non lues sont conservées)."""
    count = await repository.delete_read(db, current_user.id)
    await db.commit()
    return Message(detail=f"{count} notification(s) supprimée(s).")


async def _authenticate_ws(token: str) -> User | None:
    try:
        payload = decode_token(token, TokenType.ACCESS)
        user_id = uuid.UUID(payload["sub"])
    except (InvalidTokenError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return user


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    user = await _authenticate_ws(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(user.id, websocket)
    try:
        while True:
            # Le client n'envoie rien — on attend juste la déconnexion. Un
            # ping/pong applicatif n'est pas nécessaire : le protocole
            # WebSocket a son propre ping/pong géré par le serveur ASGI.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(user.id, websocket)
