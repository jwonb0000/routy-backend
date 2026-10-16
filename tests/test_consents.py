# 약관·민감정보·마케팅 동의 테스트

from conftest import ALL_REQUIRED_AGREEMENTS, DEFAULT_PASSWORD, bearer, code_in


def _verified_signup_body(client, outbox, email="user1@gmail.com", **fields):
    client.post("/send-verification-email", json={"email": email})
    client.post("/verify-email", json={"email": email, "code": code_in(outbox[-1])})
    return {
        "username": "routy01",
        "email": email,
        "password": DEFAULT_PASSWORD,
        "language": "ja",
        "age_group": "20s",
        **fields,
    }


def test_signup_requires_required_agreements(client, outbox):
    body = _verified_signup_body(
        client,
        outbox,
        agreements={"terms": True, "privacy": False, "age_over_14": False},
    )
    response = client.post("/signup", json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "CONSENT_REQUIRED"
    assert response.json()["missing"] == ["privacy", "age_over_14"]


def test_sensitive_info_needs_its_own_agreement(client, outbox):
    body = _verified_signup_body(
        client,
        outbox,
        avoided_ingredients=["fragrance"],
        agreements={**ALL_REQUIRED_AGREEMENTS, "sensitive_info": False},
    )
    response = client.post("/signup", json=body)

    assert response.json()["code"] == "CONSENT_REQUIRED"
    assert response.json()["missing"] == ["sensitive_info"]


def test_signup_without_sensitive_info_does_not_need_that_agreement(client, outbox):
    body = _verified_signup_body(
        client,
        outbox,
        agreements={**ALL_REQUIRED_AGREEMENTS, "sensitive_info": False},
    )
    response = client.post("/signup", json=body)

    assert response.status_code == 200
    assert response.json()["sensitive_info_agreed"] is False


def test_signup_records_agreements(signup):
    user = signup(agreements={**ALL_REQUIRED_AGREEMENTS, "marketing": True})

    assert user["terms_version"]
    assert user["privacy_version"]
    assert user["sensitive_info_agreed"] is True
    assert user["marketing_agreed"] is True


def test_patch_sensitive_info_requires_agreement(client, signup, login):
    signup(agreements={**ALL_REQUIRED_AGREEMENTS, "sensitive_info": False})
    token = login().json()["access_token"]

    response = client.patch("/users/me", headers=bearer(token), json={"avoided_ingredients": ["ethanol"]})
    assert response.json()["code"] == "CONSENT_REQUIRED"

    response = client.put("/users/me/consents", headers=bearer(token), json={"sensitive_info": True})
    assert response.json()["sensitive_info_agreed"] is True

    response = client.patch("/users/me", headers=bearer(token), json={"avoided_ingredients": ["ethanol"]})
    assert response.status_code == 200
    assert response.json()["avoided_ingredients"] == ["ethanol"]


def test_withdrawing_sensitive_agreement_erases_that_data(client, signup, login):
    signup(sensitivity="SOMETIMES", avoided_ingredients=["fragrance"])
    token = login().json()["access_token"]

    response = client.put("/users/me/consents", headers=bearer(token), json={"sensitive_info": False})
    body = response.json()

    assert body["sensitive_info_agreed"] is False
    assert body["avoided_ingredients"] == []
    assert body["sensitivity"] == "NONE"


def test_marketing_toggle(client, signup, login):
    signup()
    token = login().json()["access_token"]

    response = client.put("/users/me/consents", headers=bearer(token), json={"marketing": True})
    assert response.json()["marketing_agreed"] is True

    response = client.put("/users/me/consents", headers=bearer(token), json={"marketing": False})
    assert response.json()["marketing_agreed"] is False


def test_sensitivity_alone_needs_sensitive_agreement(client, outbox):
    body = _verified_signup_body(
        client,
        outbox,
        sensitivity="SOMETIMES",
        agreements={**ALL_REQUIRED_AGREEMENTS, "sensitive_info": False},
    )
    response = client.post("/signup", json=body)

    assert response.json()["code"] == "CONSENT_REQUIRED"
    assert response.json()["missing"] == ["sensitive_info"]
