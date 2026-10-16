# 회원가입·이메일 인증·로그인·아이디 찾기 테스트

from conftest import ALL_REQUIRED_AGREEMENTS, DEFAULT_PASSWORD, code_in, wrong_code_for


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200


def test_check_username(client, signup):
    response = client.post("/check-username", json={"username": "routy01"})
    assert response.json()["available"] is True

    signup(username="routy01")

    response = client.post("/check-username", json={"username": "routy01"})
    assert response.json()["available"] is False


def test_signup_saves_profile(signup):
    user = signup(
        email="  User1@Gmail.com ",
        skin_type="COMBINATION",
        sensitivity="OFTEN",
        avoided_ingredients=["fragrance", "paraben", "fragrance"],
    )

    assert user["email"] == "user1@gmail.com"
    assert user["language"] == "ja"
    assert user["age_group"] == "20s"
    assert user["skin_type"] == "COMBINATION"
    assert user["sensitivity"] == "OFTEN"
    assert user["avoided_ingredients"] == ["fragrance", "paraben"]
    assert user["is_email_verified"] is True
    assert "password_hash" not in user


def test_signup_skip_optional_fields(signup):
    user = signup()
    assert user["skin_type"] is None
    assert user["sensitivity"] == "NONE"
    assert user["avoided_ingredients"] == []


def test_signup_requires_email_verification(client):
    response = client.post(
        "/signup",
        json={
            "username": "routy01",
            "email": "user1@gmail.com",
            "password": DEFAULT_PASSWORD,
            "language": "ja",
            "age_group": "20s",
            "agreements": ALL_REQUIRED_AGREEMENTS,
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_duplicate_username_and_email(client, signup, outbox):
    signup(username="routy01", email="user1@gmail.com")

    response = client.post("/send-verification-email", json={"email": "user1@gmail.com"})
    assert response.json()["code"] == "EMAIL_TAKEN"

    client.post("/send-verification-email", json={"email": "user2@gmail.com"})
    client.post("/verify-email", json={"email": "user2@gmail.com", "code": code_in(outbox[-1])})
    response = client.post(
        "/signup",
        json={
            "username": "routy01",
            "email": "user2@gmail.com",
            "password": DEFAULT_PASSWORD,
            "language": "zh-CN",
            "age_group": "30s",
            "agreements": ALL_REQUIRED_AGREEMENTS,
        },
    )
    assert response.json()["code"] == "USERNAME_TAKEN"


def test_verification_email_language(client, outbox):
    client.post("/send-verification-email", json={"email": "user1@gmail.com", "lang": "ja"})
    assert outbox[-1]["subject"] == "[Routy] メール認証コード"
    assert outbox[-1]["to"] == "user1@gmail.com"


def test_resend_cooldown(client):
    client.post("/send-verification-email", json={"email": "user1@gmail.com"})
    response = client.post("/send-verification-email", json={"email": "user1@gmail.com"})

    assert response.status_code == 429
    assert response.json()["code"] == "CODE_RESEND_TOO_SOON"
    assert response.json()["retry_after"] > 0


def test_wrong_code_attempt_limit(client, outbox):
    client.post("/send-verification-email", json={"email": "user1@gmail.com"})
    wrong = wrong_code_for(code_in(outbox[-1]))

    for remaining in [4, 3, 2, 1]:
        response = client.post("/verify-email", json={"email": "user1@gmail.com", "code": wrong})
        assert response.status_code == 400
        assert response.json()["code"] == "CODE_MISMATCH"
        assert response.json()["remaining_attempts"] == remaining

    response = client.post("/verify-email", json={"email": "user1@gmail.com", "code": wrong})
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_ATTEMPTS"

    response = client.post("/verify-email", json={"email": "user1@gmail.com", "code": wrong})
    assert response.json()["code"] == "VERIFICATION_NOT_FOUND"


def test_invalid_input_returns_validation_error(client):
    response = client.post(
        "/signup",
        json={
            "username": "ab",
            "email": "not-an-email",
            "password": "비밀번호abc123",
            "language": "jp",
            "age_group": "20s",
        },
    )
    body = response.json()

    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    fields = {error["field"] for error in body["errors"]}
    assert {"username", "email", "password", "language"} <= fields


def test_login_and_remember_me(signup, login):
    signup()

    response = login(remember_me=False)
    assert response.status_code == 200
    assert response.json()["expires_in"] == 24 * 60 * 60

    response = login(remember_me=True)
    assert response.json()["expires_in"] == 30 * 24 * 60 * 60


def test_login_wrong_password(signup, login):
    signup()
    response = login(password="wrong1234")

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_username(login):
    response = login(username="nobody")
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_five_failures_block_only_that_ip(signup, login, use_ip):
    signup()
    use_ip("10.0.0.1")

    for _ in range(4):
        assert login(password="wrong1234").json()["code"] == "INVALID_CREDENTIALS"

    response = login(password="wrong1234")
    assert response.status_code == 429
    assert response.json()["code"] == "TOO_MANY_LOGIN_ATTEMPTS"

    response = login()
    assert response.json()["code"] == "TOO_MANY_LOGIN_ATTEMPTS"
    assert response.json()["retry_after"] > 0

    use_ip("10.0.0.2")
    assert login().status_code == 200


def test_unknown_username_failures_are_counted(login, use_ip):
    use_ip("10.0.0.1")
    for _ in range(4):
        assert login(username="nobody").json()["code"] == "INVALID_CREDENTIALS"
    assert login(username="nobody").json()["code"] == "TOO_MANY_LOGIN_ATTEMPTS"


def test_account_locks_after_failures_from_many_ips(signup, login, use_ip):
    signup()

    for ip_number in range(1, 4):
        use_ip(f"10.0.0.{ip_number}")
        for _ in range(5):
            login(password="wrong1234")

    use_ip("10.0.0.4")
    for _ in range(4):
        assert login(password="wrong1234").json()["code"] == "INVALID_CREDENTIALS"
    response = login(password="wrong1234")
    assert response.json()["code"] == "ACCOUNT_LOCKED"

    use_ip("10.0.0.99")
    response = login()
    assert response.status_code == 429
    assert response.json()["code"] == "ACCOUNT_LOCKED"


def test_email_sending_is_limited_per_ip(client, use_ip):
    use_ip("10.0.0.1")
    for number in range(5):
        response = client.post("/send-verification-email", json={"email": f"user{number}@gmail.com"})
        assert response.status_code == 200

    response = client.post("/send-verification-email", json={"email": "user9@gmail.com"})
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert response.json()["retry_after"] > 0

    use_ip("10.0.0.2")
    response = client.post("/send-verification-email", json={"email": "user9@gmail.com"})
    assert response.status_code == 200


def test_email_limit_is_shared_across_email_endpoints(client, signup, use_ip):
    signup(email="user1@gmail.com")
    use_ip("10.0.0.1")

    for _ in range(3):
        client.post("/find-username", json={"email": "user1@gmail.com"})
    client.post("/password-reset/send-code", json={"username": "routy01", "email": "user1@gmail.com"})
    client.post("/send-verification-email", json={"email": "user2@gmail.com"})

    response = client.post("/find-username", json={"email": "user1@gmail.com"})
    assert response.json()["code"] == "RATE_LIMITED"
