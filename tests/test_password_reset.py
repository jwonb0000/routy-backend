# 비밀번호 재설정(비밀번호 찾기) 테스트

from conftest import DEFAULT_PASSWORD, bearer, code_in

NEW_PASSWORD = "Newpass5678!"


def _get_reset_token(client, outbox, username="routy01", email="user1@gmail.com"):
    response = client.post(
        "/password-reset/send-code",
        json={"username": username, "email": email, "lang": "zh-CN"},
    )
    assert response.status_code == 200, response.json()
    assert outbox[-1]["subject"] == "[Routy] 重置密码验证码"

    response = client.post(
        "/password-reset/verify-code",
        json={"email": email, "code": code_in(outbox[-1])},
    )
    assert response.status_code == 200, response.json()
    return response.json()["reset_token"]


def test_full_reset_flow(client, outbox, signup, login):
    signup()
    old_token = login().json()["access_token"]

    reset_token = _get_reset_token(client, outbox)
    response = client.post(
        "/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200

    assert login(password=DEFAULT_PASSWORD).json()["code"] == "INVALID_CREDENTIALS"
    assert login(password=NEW_PASSWORD).status_code == 200

    response = client.get("/users/me", headers=bearer(old_token))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_reset_token_is_single_use(client, outbox, signup):
    signup()
    reset_token = _get_reset_token(client, outbox)

    first = client.post(
        "/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": NEW_PASSWORD},
    )
    second = client.post(
        "/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": "Another9999!"},
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["code"] == "INVALID_RESET_TOKEN"


def test_reset_clears_login_blocks(client, outbox, signup, login):
    signup()
    for _ in range(5):
        login(password="wrong1234")
    assert login().json()["code"] == "TOO_MANY_LOGIN_ATTEMPTS"

    reset_token = _get_reset_token(client, outbox)
    client.post(
        "/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": NEW_PASSWORD},
    )

    assert login(password=NEW_PASSWORD).status_code == 200


def test_reset_unlocks_account(client, outbox, signup, login, use_ip):
    signup()
    for ip_number in range(1, 5):
        use_ip(f"10.0.0.{ip_number}")
        for _ in range(5):
            login(password="wrong1234")
    assert login().json()["code"] == "ACCOUNT_LOCKED"

    use_ip("10.0.0.50")
    reset_token = _get_reset_token(client, outbox)
    client.post(
        "/password-reset/confirm",
        json={"reset_token": reset_token, "new_password": NEW_PASSWORD},
    )

    use_ip("10.0.0.1")
    assert login(password=NEW_PASSWORD).status_code == 200


def test_wrong_username_email_pair(client, signup):
    signup(username="routy01", email="user1@gmail.com")

    response = client.post(
        "/password-reset/send-code",
        json={"username": "routy01", "email": "other@gmail.com"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


def test_reset_token_is_not_a_login_token(client, outbox, signup):
    signup()
    reset_token = _get_reset_token(client, outbox)

    response = client.get("/users/me", headers=bearer(reset_token))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"

