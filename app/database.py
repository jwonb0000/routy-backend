# DB 연결: SQLite 파일(routy.db)에 연결하고, 요청마다 DB 세션을 열고 닫는다.

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 모든 테이블(models.py)이 상속받는 기본 클래스
class Base(DeclarativeBase):
    pass


# API 요청 하나당 DB 세션 하나를 열고, 끝나면 자동으로 닫는다
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
