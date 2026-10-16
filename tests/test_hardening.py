# 보안 보강 테스트: 아이디 대소문자, 비밀번호 추측 제한, 탈퇴 후 토큰, 입력 길이 제한, 에러 형식

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from conftest import ALL_REQUIRED_AGREEMENTS, DEFAULT_PASSWORD, bearer, code_in
from app.database import SessionLocal
from app.models import EmailVerification

NEW_PASSWORD = "Newpass5678!"


def test_username_is_stored_lowercase(signup):
    user = signup(username="Routy01")
    assert user["username"] == "routy01"


def test_username_login_ignores_case(signup, login):
    signup(username="routy01")
    assert login(username="ROUTY01").status_code == 200


def test_username_check_ignores_case(client, signup):
    signup(username="routy01")
    response = client.post("/check-username", json={"username": "RoUtY01"})
    assert response.json()["available"] is False


def test_username_case_variant_cannot_sign_up_twice(client, outbox, signup):
    signup(username="routy01", email="user1@gmail.com")

    client.post("/send-verification-email", json={"email": "user2@gmail.com"})
    client.post("/verify-email", json={"email": "user2@gmail.com", "code": code_in(outbox[-1])})
    response = client.post(
        "/signup",
        json={
            "username": "ROUTY01",
            "email": "user2@gmail.com",
            "password": DEFAULT_PASSWORD,
            "language": "ja",
            "age_group": "20s",
            "agreements": ALL_REQUIRED_AGREEMENTS,
        },
    )
    assert response.json()["code"] == "USERNAME_TAKEN"


def test_username_rejects_other_characters(client):
    for username in ["routy_01", "ro uty01", "루티1234", "routy<b>", "abc"]:
        response = client.post("/check-username", json={"username": username})
        assert response.status_code == 422, username
        assert response.json()["errors"][0]["field"] == "username"


def test_password_reset_ignores_username_case(client, signup):
    signup(username="routy01", email="user1@gmail.com")
    response = client.post(
        "/password-reset/send-code",
        json={"username": "Routy01", "email": "user1@gmail.com"},
    )
    assert response.status_code == 200


def test_current_password_guessing_is_limited(client, signup, login):
    signup()
    token = login().json()["access_token"]

    for _ in range(4):
        response = client.put(
            "/users/me/password",
            headers=bearer(token),
            json={"current_password": "wrong1234", "new_password": NEW_PASSWORD},
        )
        assert response.json()["code"] == "WRONG_CURRENT_PASSWORD"

    response = client.request(
        "DELETE",
        "/users/me",
        headers=bearer(token),
        json={"password": "wrong1234"},
    )
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_PASSWORD_ATTEMPTS"

    response = client.put(
        "/users/me/password",
        headers=bearer(token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.json()["code"] == "TOO_MANY_PASSWORD_ATTEMPTS"
    assert response.json()["retry_after"] > 0


def test_correct_password_resets_guess_counter(client, signup, login):
    signup()
    token = login().json()["access_token"]

    for _ in range(4):
        client.put(
            "/users/me/password",
            headers=bearer(token),
            json={"current_password": "wrong1234", "new_password": NEW_PASSWORD},
        )

    response = client.put(
        "/users/me/password",
        headers=bearer(token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]

    response = client.put(
        "/users/me/password",
        headers=bearer(new_token),
        json={"current_password": "wrong1234", "new_password": "Another9999!"},
    )
    assert response.json()["code"] == "WRONG_CURRENT_PASSWORD"


def test_expired_verifications_are_purged(client):
    client.post("/send-verification-email", json={"email": "old@gmail.com"})

    with SessionLocal() as db:
        record = db.scalar(select(EmailVerification).where(EmailVerification.email == "old@gmail.com"))
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    client.post("/send-verification-email", json={"email": "new@gmail.com"})

    with SessionLocal() as db:
        emails = set(db.scalars(select(EmailVerification.email)))
    assert emails == {"new@gmail.com"}


def test_deleted_user_token_cannot_reach_new_user(client, signup, login):
    signup(username="first01", email="first@gmail.com")
    deleted_user = signup(username="second01", email="second@gmail.com")
    old_token = login(username="second01").json()["access_token"]

    client.request(
        "DELETE",
        "/users/me",
        headers=bearer(old_token),
        json={"password": DEFAULT_PASSWORD},
    )
    new_user = signup(username="third01", email="third@gmail.com")
    assert new_user["id"] != deleted_user["id"]

    response = client.get("/users/me", headers=bearer(old_token))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_oversized_inputs_are_rejected(client, signup, login):
    signup()
    response = login(password="a1" * 100)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"

    response = client.post(
        "/password-reset/confirm",
        json={"reset_token": "x" * 5000, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 422


def test_unknown_route_uses_error_format(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_wrong_method_uses_error_format(client):
    response = client.get("/login")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"
