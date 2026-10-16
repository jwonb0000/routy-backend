# 서버 시작점: 앱을 만들고 설정·에러 처리·API 묶음(router)을 연결한다.
# 실행: uvicorn app.main:app --reload

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.database import Base, SessionLocal, engine
from app.errors import register_error_handlers
from app.routers import auth, password_reset, users
from app.verification import purge_expired_verifications

# 서버가 켜질 때: 테이블 생성 + 만료된 인증 기록 정리
Base.metadata.create_all(bind=engine)

with SessionLocal() as startup_db:
    purge_expired_verifications(startup_db)

app = FastAPI(title="Routy API")

# 프론트엔드(localhost:3000 등)에서 이 API를 부를 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 에러 응답 형식 통일 (errors.py)
register_error_handlers(app)

# API 묶음 연결: 가입·로그인 / 비밀번호 재설정 / 내 정보
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(users.router)


@app.get("/")
def home():
    return {"message": "Routy Backend"}
