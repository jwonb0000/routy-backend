# 테스트 공통 준비: 테스트용 임시 DB·설정, 가짜 메일함(outbox), 가입·로그인 도우미
# 실행: 프로젝트 폴더에서 pytest

import os
import re
import tempfile
from pathlib import Path

import pytest

_test_dir = tempfile.mkdtemp(prefix="routy-test-")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789abcdef"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_dir, 'test.db').as_posix()}"
os.environ["GMAIL_ADDRESS"] = "sender@gmail.com"
os.environ["GMAIL_PASSWORD"] = "not-used-in-tests"
os.environ["BCRYPT_ROUNDS"] = "4"

from fastapi.testclient import TestClient

from app import rate_limit
from app.database import Base, engine
from app.main import app
from app.routers import auth as auth_router
from app.routers import password_reset as password_reset_router

DEFAULT_PASSWORD = "Abcd1234!"
ALL_REQUIRED_AGREEMENTS = {
    "terms": True,
    "privacy": True,
    "age_over_14": True,
    "sensitive_info": True,
    "marketing": False,
}


@pytest.fixture(autouse=True)
def fresh_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    rate_limit.limiter.reset()
    yield


@pytest.fixture
def use_ip(monkeypatch):
    def _use_ip(ip: str):
        monkeypatch.setattr(rate_limit, "client_ip", lambda request: ip)

    return _use_ip


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send_email(recipient_email, subject, body):
        sent.append({"to": recipient_email, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(auth_router, "send_email", fake_send_email)
    monkeypatch.setattr(password_reset_router, "send_email", fake_send_email)
    return sent


@pytest.fixture
def client(outbox):
    with TestClient(app) as test_client:
        yield test_client


def code_in(mail: dict) -> str:
    return re.search(r"\d{6}", mail["body"]).group()


def wrong_code_for(code: str) -> str:
    return "000000" if code != "000000" else "111111"


@pytest.fixture
def signup(client, outbox):
    def _signup(username="routy01", email="user1@gmail.com", password=DEFAULT_PASSWORD, **fields):
        response = client.post("/send-verification-email", json={"email": email})
        assert response.status_code == 200, response.json()

        response = client.post("/verify-email", json={"email": email, "code": code_in(outbox[-1])})
        assert response.status_code == 200, response.json()

        body = {
            "username": username,
            "email": email,
            "password": password,
            "language": "ja",
            "age_group": "20s",
            "agreements": ALL_REQUIRED_AGREEMENTS,
            **fields,
        }
        response = client.post("/signup", json=body)
        assert response.status_code == 200, response.json()
        return response.json()

    return _signup


@pytest.fixture
def login(client):
    def _login(username="routy01", password=DEFAULT_PASSWORD, remember_me=False):
        return client.post(
            "/login",
            json={"username": username, "password": password, "remember_me": remember_me},
        )

    return _login


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
