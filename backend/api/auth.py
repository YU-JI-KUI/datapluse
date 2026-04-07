"""
简化版认证模块
- 单超级管理员（从 config.yaml 读取）
- JWT Token（HS256）
- 依赖注入：get_current_user
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config.settings import get_settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_EXPIRE_HOURS = 24


# ── Schemas ────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str


class UserInfo(BaseModel):
    username: str
    role: str = "admin"


# ── Token 工具 ─────────────────────────────────────────────────────────────

def _create_token(data: dict) -> str:
    settings = get_settings()
    payload = dict(data)
    payload["exp"] = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def _verify_token(token: str) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise ValueError("no sub")
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── 依赖注入 ───────────────────────────────────────────────────────────────

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> UserInfo:
    username = _verify_token(token)
    return UserInfo(username=username)


# ── 路由 ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    settings = get_settings()
    if (
        form.username != settings.admin_username
        or form.password != settings.admin_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = _create_token({"sub": form.username})
    return Token(
        access_token=token,
        token_type="bearer",
        username=form.username,
    )


@router.get("/me", response_model=UserInfo)
async def me(user: Annotated[UserInfo, Depends(get_current_user)]):
    return user
