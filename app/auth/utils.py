from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings

_ALGORITHM = "HS256"
_EXPIRY_HOURS = 24


def hash_password(plain: str) -> str:
    # bcrypt silently truncates at 72 bytes; enforce it explicitly to avoid surprises.
    encoded = plain.encode()[:72]
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode()[:72]
    return bcrypt.checkpw(encoded, hashed.encode())


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])
