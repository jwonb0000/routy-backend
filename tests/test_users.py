# 내 정보 조회·수정·비밀번호 변경 테스트

from conftest import DEFAULT_PASSWORD, bearer

NEW_PASSWORD = "Newpass5678!"


def _token(signup, login, remember_me=False):
    signup()
    return login(remember_me=remember_me).json()["access_token"]


def test_me_requires_login(client):
    response = client.get("/users/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_me_rejects_garbage_token(client):
    response = client.get("/users/me", headers=bearer("not-a-real-token"))
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


def test_get_me(client, signup, login):
    token = _token(signup, login)
    response = client.get("/users/me", headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["username"] == "routy01"


def test_update_me(client, signup, login):
    token = _token(signup, login)

    response = client.patch(
        "/users/me",
        headers=bearer(token),
        json={"skin_type": "DRY", "sensitivity": "SOMETIMES", "avoided_ingredients": ["ethanol"]},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["skin_type"] == "DRY"
    assert body["sensitivity"] == "SOMETIMES"
    assert body["avoided_ingredients"] == ["ethanol"]
    assert body["language"] == "ja"

    response = client.patch("/users/me", headers=bearer(token), json={"skin_type": None})
    assert response.json()["skin_type"] is None


def test_update_me_rejects_null_required_field(client, signup, login):
    token = _token(signup, login)
    response = client.patch("/users/me", headers=bearer(token), json={"language": None})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_change_password(client, signup, login):
    old_token = _token(signup, login, remember_me=True)

    response = client.put(
        "/users/me/password",
        headers=bearer(old_token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert response.json()["expires_in"] == 30 * 24 * 60 * 60

    assert client.get("/users/me", headers=bearer(old_token)).json()["code"] == "INVALID_TOKEN"
    assert client.get("/users/me", headers=bearer(new_token)).status_code == 200

    assert login(password=DEFAULT_PASSWORD).json()["code"] == "INVALID_CREDENTIALS"
    assert login(password=NEW_PASSWORD).status_code == 200


def test_change_password_wrong_current(client, signup, login):
    token = _token(signup, login)
    response = client.put(
        "/users/me/password",
        headers=bearer(token),
        json={"current_password": "wrong1234", "new_password": NEW_PASSWORD},
    )
    assert response.json()["code"] == "WRONG_CURRENT_PASSWORD"


def test_change_password_same_as_current(client, signup, login):
    token = _token(signup, login)
    response = client.put(
        "/users/me/password",
        headers=bearer(token),
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert response.json()["code"] == "SAME_AS_CURRENT_PASSWORD"
