from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import decode_access_token
from app.db.models import User
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)

_401 = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise _401
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload["sub"]
    except Exception:
        raise _401

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise _401
    return user
