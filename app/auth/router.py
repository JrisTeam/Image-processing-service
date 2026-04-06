from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse, UserOut

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if not body.username or not body.username.strip():
        raise HTTPException(status_code=422, detail="Username must not be empty")
    if not body.password or not body.password.strip():
        raise HTTPException(status_code=422, detail="Password must not be empty")

    existing = await db.scalar(select(User).where(User.username == body.username))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(username=body.username, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return RegisterResponse(
        user=UserOut(id=user.id, username=user.username, created_at=user.created_at),
        access_token=token,
        token_type="bearer",
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user.id)
    return LoginResponse(
        user=UserOut(id=user.id, username=user.username, created_at=user.created_at),
        access_token=token,
        token_type="bearer",
    )
