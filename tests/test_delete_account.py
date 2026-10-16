# 회원탈퇴 테스트

from conftest import DEFAULT_PASSWORD, bearer


def _delete(client, token, password):
    return client.request(
        "DELETE",
        "/users/me",
        headers=bearer(token),
        json={"password": password},
    )


def test_delete_requires_login(client):
    response = client.request("DELETE", "/users/me", json={"password": DEFAULT_PASSWORD})
    assert response.json()["code"] == "UNAUTHORIZED"


def test_delete_requires_correct_password(client, signup, login):
    signup()
    token = login().json()["access_token"]

    response = _delete(client, token, "wrong1234")
    assert response.status_code == 400
    assert response.json()["code"] == "WRONG_CURRENT_PASSWORD"

    assert client.get("/users/me", headers=bearer(token)).status_code == 200


def test_delete_removes_account(client, signup, login):
    signup()
    token = login().json()["access_token"]

    response = _delete(client, token, DEFAULT_PASSWORD)
    assert response.status_code == 200

    assert client.get("/users/me", headers=bearer(token)).json()["code"] == "INVALID_TOKEN"
    assert login().json()["code"] == "INVALID_CREDENTIALS"
    assert client.post("/check-username", json={"username": "routy01"}).json()["available"] is True


def test_can_sign_up_again_after_deletion(client, signup, login):
    signup(username="routy01", email="user1@gmail.com")
    token = login().json()["access_token"]
    _delete(client, token, DEFAULT_PASSWORD)

    user = signup(username="routy01", email="user1@gmail.com")
    assert user["username"] == "routy01"
