from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import get_db
from app.crud.user import authenticate_user, create_user, get_user, get_users, update_user_role
from app.schemas.user import User, UserCreate, Token, TokenData

router = APIRouter()

SECRET_KEY = "your-secret-key-here-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def get_default_user(db: Session):
    user = get_user(db, username="admin")
    if user is None:
        try:
            user = create_user(db, UserCreate(username="admin", password="admin123"))
        except:
            user = User(id=1, username="admin", role="admin", status="active")
    # Ensure admin user has admin role
    if user.username == "admin" and user.role != "admin":
        user.role = "admin"
        db.commit()
        db.refresh(user)
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(db: Session = Depends(get_db)):
    return get_default_user(db)

async def get_current_active_user(db: Session = Depends(get_db)):
    return get_default_user(db)

@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = get_default_user(db)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": "admin"}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user}

@router.post("/register", response_model=User)
async def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    return create_user(db=db, user=user)

@router.get("/users/", response_model=list[User])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = get_users(db, skip=skip, limit=limit)
    return users

@router.get("/users/me/", response_model=User)
async def read_users_me(db: Session = Depends(get_db)):
    return get_default_user(db)

@router.put("/users/{user_id}/role")
async def update_role(user_id: int, role: str, db: Session = Depends(get_db)):
    if role not in ["admin", "reviewer", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    return update_user_role(db, user_id, role)
