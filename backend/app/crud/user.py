from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.user import User
from app.schemas.user import UserCreate, UserCreateWithDetails, UserUpdate
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["sha256_crypt", "bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = User(username=user.username, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def create_user_with_details(db: Session, data: UserCreateWithDetails):
    db_user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        display_name=data.display_name,
        role=data.role,
        status=data.status,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if user.status != "active":
        return None
    return user


def apply_user_filters(query, search: str = None, role: str = None, status: str = None):
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.display_name.ilike(keyword),
            )
        )
    if role:
        query = query.filter(User.role == role)
    if status:
        query = query.filter(User.status == status)
    return query


def get_users(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    search: str = None,
    role: str = None,
    status: str = None,
):
    q = apply_user_filters(db.query(User), search=search, role=role, status=status)
    return q.order_by(User.id).offset(skip).limit(limit).all()


def count_users(db: Session, search: str = None, role: str = None, status: str = None):
    q = apply_user_filters(db.query(User), search=search, role=role, status=status)
    return q.count()


def count_admin_users(db: Session, active_only: bool = False):
    q = db.query(User).filter(User.role == "admin")
    if active_only:
        q = q.filter(User.status == "active")
    return q.count()


def update_user(db: Session, user_id: int, data: UserUpdate):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.role is not None:
        user.role = data.role
    if data.status is not None:
        user.status = data.status
    db.commit()
    db.refresh(user)
    return user


def update_user_status(db: Session, user_id: int, status: str):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.status = status
    db.commit()
    db.refresh(user)
    return user


def reset_user_password(db: Session, user_id: int, new_password: str):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.password_hash = get_password_hash(new_password)
    db.commit()
    db.refresh(user)
    return user
