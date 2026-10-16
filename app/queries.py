# 자주 쓰는 DB 조회: 아이디로 회원 찾기, 이메일로 회원 찾기.

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))
