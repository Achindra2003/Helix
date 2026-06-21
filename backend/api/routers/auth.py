from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..errors import api_error
from ..models import User
from ..schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest, session: AsyncSession = Depends(get_session)
):
    exists = await session.scalar(select(User).where(User.email == body.email))
    if exists:
        raise api_error(409, "conflict", "Email already registered.")

    user = User(email=body.email, pw_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.pw_hash):
        raise api_error(401, "unauthorized", "Invalid email or password.")

    return AuthResponse(user=UserOut.model_validate(user, from_attributes=True),
                        token=make_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user, from_attributes=True)
