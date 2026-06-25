import re

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import get_db
from app.crud import user as user_crud
from app.schemas.user import (
    UserCreate, UserCreateWithDetails, UserUpdate, UserPasswordReset,
    UserLogin, UserOut, UserListOut, Token, TokenData,
)

router = APIRouter()

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
PASSWORD_PATTERN = re.compile(r"^\S{8,32}$")
VALID_ROLES = {"admin", "writer", "reviewer"}
VALID_STATUS = {"active", "disabled"}

SECRET_KEY = "your-secret-key-here-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="无效的登录凭证")
    except JWTError:
        raise HTTPException(status_code=401, detail="登录凭证已过期")
    user = user_crud.get_user(db, username=username)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


async def get_current_active_user(
    current_user: UserOut = Depends(get_current_user),
):
    if current_user.status != "active":
        raise HTTPException(status_code=403, detail="账号已被禁用")
    return current_user


def get_default_user(db: Session):
    """向后兼容：获取 admin 用户，供其他模块调用"""
    return user_crud.get_user(db, username="admin")


def require_admin(current_user: UserOut = Depends(get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return current_user


def normalize_username(username: str) -> str:
    normalized = (username or "").strip()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="用户名需为 3-20 位字母、数字或下划线")
    return normalized


def validate_password(password: str) -> str:
    normalized = password or ""
    if not PASSWORD_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="密码需为 8-32 位，且不能包含空格")
    return normalized


def normalize_display_name(display_name: str) -> str:
    normalized = (display_name or "").strip()
    if len(normalized) < 2 or len(normalized) > 20:
        raise HTTPException(status_code=400, detail="真实姓名长度需为 2-20 个字符")
    return normalized


def validate_role(role: str) -> str:
    normalized = (role or "").strip()
    if normalized not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="角色值无效")
    return normalized


def validate_status_value(status_value: str) -> str:
    normalized = (status_value or "").strip()
    if normalized not in VALID_STATUS:
        raise HTTPException(status_code=400, detail="状态值无效，仅支持 active 或 disabled")
    return normalized


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = (form_data.username or "").strip()
    password = form_data.password or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="请输入用户名和密码")
    user = user_crud.authenticate_user(db, username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserOut.model_validate(user),
    }


@router.post("/register", response_model=UserOut)
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
    username = normalize_username(user.username)
    password = validate_password(user.password)
    db_user = user_crud.get_user(db, username=username)
    if db_user:
        raise HTTPException(status_code=409, detail="用户名已存在")
    user.username = username
    user.password = password
    return user_crud.create_user(db=db, user=user)


# ─── 用户管理 ─────────────────────────────────────────────


@router.get("/users", response_model=UserListOut)
async def list_users(
    search: str = Query(None, description="按用户名或真实姓名搜索"),
    role: str = Query(None, description="按角色筛选"),
    status: str = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    skip = (page - 1) * page_size
    items = user_crud.get_users(db, skip=skip, limit=page_size, search=search, role=role, status=status)
    total = user_crud.count_users(db, search=search, role=role, status=status)
    return UserListOut(items=[UserOut.model_validate(u) for u in items], total=total)


@router.post("/users", response_model=UserOut)
async def create_user_api(
    data: UserCreateWithDetails,
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    data.username = normalize_username(data.username)
    data.password = validate_password(data.password)
    data.display_name = normalize_display_name(data.display_name)
    data.role = validate_role(data.role)
    data.status = validate_status_value(data.status)
    existing = user_crud.get_user(db, username=data.username)
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return user_crud.create_user_with_details(db, data)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user_api(
    user_id: int,
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    user = user_crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.put("/users/{user_id}", response_model=UserOut)
async def update_user_api(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(require_admin),
):
    existing_user = user_crud.get_user_by_id(db, user_id)
    if not existing_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if data.display_name is not None:
        data.display_name = normalize_display_name(data.display_name)
    if data.role is not None:
        data.role = validate_role(data.role)
    if data.status is not None:
        data.status = validate_status_value(data.status)

    next_role = data.role if data.role is not None else existing_user.role
    next_status = data.status if data.status is not None else existing_user.status

    if current_user.id == user_id:
        if next_role != "admin":
            raise HTTPException(status_code=400, detail="当前登录管理员需保留管理员角色")
        if next_status != "active":
            raise HTTPException(status_code=400, detail="当前登录管理员需保持启用状态")

    if existing_user.role == "admin" and (next_role != "admin" or next_status != "active"):
        if user_crud.count_admin_users(db, active_only=True) <= 1 and existing_user.status == "active":
            raise HTTPException(status_code=400, detail="系统至少需要保留一个启用中的管理员账号")

    user = user_crud.update_user(db, user_id, data)
    return user


@router.put("/users/{user_id}/status", response_model=UserOut)
async def toggle_user_status(
    user_id: int,
    status: str = Query(..., description="active 或 disabled"),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(require_admin),
):
    status = validate_status_value(status)
    existing_user = user_crud.get_user_by_id(db, user_id)
    if not existing_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if current_user.id == user_id and status != "active":
        raise HTTPException(status_code=400, detail="当前登录管理员需保持启用状态")
    if existing_user.role == "admin" and existing_user.status == "active" and status != "active":
        if user_crud.count_admin_users(db, active_only=True) <= 1:
            raise HTTPException(status_code=400, detail="系统至少需要保留一个启用中的管理员账号")
    user = user_crud.update_user_status(db, user_id, status)
    return user


@router.post("/users/{user_id}/reset-password", response_model=dict)
async def reset_user_password(
    user_id: int,
    data: UserPasswordReset,
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    data.new_password = validate_password(data.new_password)
    user = user_crud.reset_user_password(db, user_id, data.new_password)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "密码已重置"}


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: UserOut = Depends(get_current_active_user)):
    return current_user
