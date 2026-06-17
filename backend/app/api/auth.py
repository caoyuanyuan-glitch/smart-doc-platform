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


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = user_crud.authenticate_user(db, form_data.username, form_data.password)
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
    db_user = user_crud.get_user(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return user_crud.create_user(db=db, user=user)


# ─── 用户管理 ─────────────────────────────────────────────


@router.get("/users", response_model=UserListOut)
async def list_users(
    search: str = Query(None, description="按用户名搜索"),
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
    _: UserOut = Depends(require_admin),
):
    user = user_crud.update_user(db, user_id, data)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.put("/users/{user_id}/status", response_model=UserOut)
async def toggle_user_status(
    user_id: int,
    status: str = Query(..., description="active 或 disabled"),
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    if status not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="状态值无效，仅支持 active 或 disabled")
    user = user_crud.update_user_status(db, user_id, status)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.post("/users/{user_id}/reset-password", response_model=dict)
async def reset_user_password(
    user_id: int,
    data: UserPasswordReset,
    db: Session = Depends(get_db),
    _: UserOut = Depends(require_admin),
):
    user = user_crud.reset_user_password(db, user_id, data.new_password)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"message": "密码已重置"}


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: UserOut = Depends(get_current_active_user)):
    return current_user
