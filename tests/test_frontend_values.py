# 프론트와 맞춘 값(언어·나이대·피부타입·민감도)과 비밀번호 규칙 테스트

import pytest

from conftest import ALL_REQUIRED_AGREEMENTS, DEFAULT_PASSWORD, code_in


def _verified_signup_body(client, outbox, email="user1@gmail.com", **fields):
    client.post("/send-verification-email", json={"email": email})
    client.post("/verify-email", json={"email": email, "code": code_in(outbox[-1])})
    return {
        "username": "routy01",
        "email": email,
        "password": DEFAULT_PASSWORD,
        "language": "ja",
        "age_group": "20s",
        "agreements": ALL_REQUIRED_AGREEMENTS,
        **fields,
    }


def test_frontend_codes_are_accepted(signup):
    user = signup(language="zh-TW", age_group="50plus", skin_type="OILY")
    assert user["language"] == "zh-TW"
    assert user["age_group"] == "50plus"
    assert user["skin_type"] == "OILY"


@pytest.mark.parametrize(
    "field, value",
    [
        ("language", "zh"),
        ("language", "tw"),
        ("age_group", "10s"),
        ("age_group", "50s+"),
        ("skin_type", "dry"),
        ("sensitivity", "true"),
        ("sensitivity", "often"),
    ],
)
def test_old_codes_are_rejected(client, outbox, field, value):
    body = _verified_signup_body(client, outbox, **{field: value})
    response = client.post("/signup", json=body)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


@pytest.mark.parametrize("password", ["abcd1234", "Abcd!@#$", "12345678!", "abcd 123!", "Ab1!"])
def test_password_needs_letter_digit_and_symbol(client, outbox, password):
    body = _verified_signup_body(client, outbox, password=password)
    response = client.post("/signup", json=body)

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "password"


@pytest.mark.parametrize("password", ["abcd123!", "ROUTY2026!"])
def test_uppercase_is_optional(signup, password):
    assert signup(password=password)["username"] == "routy01"


def test_simplified_chinese_email(client, outbox):
    client.post("/send-verification-email", json={"email": "user1@gmail.com", "lang": "zh-CN"})
    assert outbox[-1]["subject"] == "[Routy] 邮箱验证码"


def test_old_chinese_code_is_rejected(client):
    response = client.post("/send-verification-email", json={"email": "user1@gmail.com", "lang": "zh"})
    assert response.status_code == 422


def test_traditional_chinese_email(client, outbox):
    client.post("/send-verification-email", json={"email": "user1@gmail.com", "lang": "zh-TW"})
    assert outbox[-1]["subject"] == "[Routy] 電子郵件驗證碼"


def test_country_is_not_stored(signup):
    assert "country" not in signup()
