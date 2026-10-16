# Routy Backend

FastAPI + SQLite 백엔드

## 처음 설정 (Windows)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

`.env`를 열어 값을 채운다. `SECRET_KEY`는 32자 이상이어야 하고(짧으면 서버가 켜지지 않음), 아래 명령으로 만든다.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

`GMAIL_PASSWORD`에는 구글 계정의 **앱 비밀번호**를 넣는다.

메일 계정이 아직 없으면 `EMAIL_BACKEND=console`로 두면 된다. 메일을 실제로 보내지 않고 서버 창에 내용(인증 코드 포함)을 출력한다. **실제 서비스에서는 반드시 `smtp`로 바꿔야 한다.** `DATABASE_URL`을 비워두면 프로젝트 폴더에 `routy.db`가 생긴다.

## 서버 실행

`routy-backend` 폴더에서 실행한다.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 문서: http://localhost:8000/docs

## 테스트

```bash
pip install -r requirements-dev.txt
pytest
```

테스트는 임시 DB를 따로 만들고 메일도 실제로 보내지 않는다. 코드를 고친 뒤에는 `pytest`로 기존 기능이 깨지지 않았는지 확인한다.

## 버전 고정

서버와 테스트가 잘 돌아가는 것을 확인했으면, 그때 설치된 정확한 버전을 기록해둔다.

```bash
pip freeze > requirements.lock
```

다른 PC에서 똑같이 설치할 때는 `pip install -r requirements.lock`을 쓴다.

## DB 초기화

서버를 끄고 `routy.db`를 삭제한 뒤 다시 실행하면 테이블이 새로 만들어진다. `app/models.py`를 바꿨을 때도 이렇게 해야 반영된다.

---

## API 목록

| API | 메서드 | 설명 | 로그인 |
|---|---|---|---|
| `/` | GET | 서버 상태 | |
| `/check-username` | POST | 아이디 중복확인 | |
| `/send-verification-email` | POST | 회원가입용 인증 코드 발송 | |
| `/verify-email` | POST | 회원가입용 인증 코드 확인 | |
| `/signup` | POST | 회원가입 | |
| `/login` | POST | 로그인 (아이디 + 비밀번호) | |
| `/find-username` | POST | 아이디를 이메일로 발송 | |
| `/password-reset/send-code` | POST | 비밀번호 재설정 인증 코드 발송 | |
| `/password-reset/verify-code` | POST | 인증 코드 확인 → `reset_token` 발급 | |
| `/password-reset/confirm` | POST | 새 비밀번호 저장 | |
| `/users/me` | GET | 내 정보 조회 | ✅ |
| `/users/me` | PATCH | 내 정보 수정 | ✅ |
| `/users/me/password` | PUT | 비밀번호 변경 → 새 `access_token` 발급 | ✅ |
| `/users/me/consents` | PUT | 마케팅·민감정보 동의 변경 | ✅ |
| `/users/me` | DELETE | 회원 탈퇴 (비밀번호 필요) | ✅ |

로그인이 필요한 API는 헤더에 `Authorization: Bearer <access_token>`을 넣는다.

## 화면별 흐름

### 회원가입

1. `POST /check-username` `{ "username": "routy01" }`
2. `POST /send-verification-email` `{ "email": "a@b.com", "lang": "ja" }`
3. `POST /verify-email` `{ "email": "a@b.com", "code": "123456" }`
4. `POST /signup`

```json
{
  "username": "routy01",
  "email": "a@b.com",
  "password": "Abcd1234!",
  "language": "ja",
  "age_group": "20s",
  "skin_type": "COMBINATION",
  "sensitivity": "SOMETIMES",
  "avoided_ingredients": ["fragrance", "paraben", "직접 입력한 성분"],
  "agreements": {
    "terms": true,
    "privacy": true,
    "age_over_14": true,
    "sensitive_info": true,
    "marketing": false
  }
}
```

`skin_type`, `sensitivity`, `avoided_ingredients`는 "건너뛰기"를 누르면 보내지 않아도 된다. 이메일 인증 후 30분 안에 가입을 끝내야 한다.

**동의 항목 (`agreements`)**

| 항목 | 필수 여부 | 화면 문구 예시 |
|---|---|---|
| `terms` | 필수 | 이용약관 동의 |
| `privacy` | 필수 | 개인정보 수집·이용 동의 |
| `age_over_14` | 필수 | 만 14세 이상입니다 |
| `sensitive_info` | 조건부 필수 | 민감정보(피부 민감도·피하고 싶은 성분) 수집·이용 동의 |
| `marketing` | 선택 | 이벤트·할인 정보 수신 동의 |

- `sensitive_info`는 `avoided_ingredients`를 보내거나 `sensitivity`를 `NONE`이 아닌 값으로 보낼 때만 필수다. "건너뛰기"를 눌렀다면 `false`여도 가입된다.
- 필수 항목이 빠지면 `CONSENT_REQUIRED`와 함께 빠진 항목 목록(`missing`)이 온다. 예: `{ "code": "CONSENT_REQUIRED", "missing": ["privacy"] }`
- 서버는 동의한 시각과 약관 버전(`app/config.py`의 `TERMS_VERSION`, `PRIVACY_VERSION`)을 저장한다. 약관 내용을 바꾸면 이 버전 값을 올린다.

### 로그인

`POST /login` `{ "username": "routy01", "password": "Abcd1234!", "remember_me": true }`

응답의 `expires_in`(초)은 토큰 유효 시간이다. `remember_me`가 `true`면 30일, 아니면 24시간이다.

로그인 실패 제한은 두 단계다.

- **같은 기기(IP)에서 한 아이디로 5번 틀리면** 그 기기에서만 15분 동안 그 아이디로 로그인할 수 없다 (`TOO_MANY_LOGIN_ATTEMPTS`). 다른 기기에서는 정상적으로 로그인된다. 그래서 남이 내 아이디로 일부러 틀려도 내 계정이 잠기지 않는다.
- **여러 기기에서 합쳐서 20번 틀리면** 계정 전체가 15분 동안 잠긴다 (`ACCOUNT_LOCKED`).

두 경우 모두 비밀번호 찾기로 새 비밀번호를 설정하면 바로 풀린다.

### 비밀번호 찾기

1. `POST /password-reset/send-code` `{ "username": "routy01", "email": "a@b.com", "lang": "ja" }`
2. `POST /password-reset/verify-code` `{ "email": "a@b.com", "code": "123456" }` → `{ "reset_token": "...", "expires_in": 900 }`
3. `POST /password-reset/confirm` `{ "reset_token": "...", "new_password": "newpass123" }`

`reset_token`은 15분 동안, 한 번만 쓸 수 있다. 비밀번호가 바뀌면 **모든 기기의 로그인이 풀린다** (기존 `access_token`이 `INVALID_TOKEN`이 됨).

### 내정보

- 수정: `PATCH /users/me`에 바꿀 항목만 보낸다. 예: `{ "skin_type": "DRY", "avoided_ingredients": ["ethanol"] }`
- `skin_type`은 `null`을 보내면 지워진다. 나머지 항목에는 `null`을 보낼 수 없다.
- 비밀번호 변경: `PUT /users/me/password` `{ "current_password": "...", "new_password": "..." }`
  - 응답으로 새 `access_token`이 온다. 기존 토큰은 모든 기기에서 무효가 되므로, 프론트는 받은 새 토큰으로 바꿔 저장한다.
- 피하고 싶은 성분을 추가하거나 `sensitivity`를 `SOMETIMES`·`OFTEN`으로 바꾸려면 민감정보 동의가 있어야 한다. 없으면 `CONSENT_REQUIRED`가 온다.

### 동의 변경

`PUT /users/me/consents`에 바꿀 항목만 보낸다.

- 마케팅 수신: `{ "marketing": true }` 또는 `{ "marketing": false }`
- 민감정보 동의: `{ "sensitive_info": true }`
- 민감정보 동의 철회: `{ "sensitive_info": false }` → **저장된 피하고 싶은 성분이 비워지고 민감도는 `NONE`으로 돌아간다.** 화면에서 한 번 더 확인을 받는 게 좋다.

`GET /users/me` 응답의 `sensitive_info_agreed`, `marketing_agreed`로 현재 동의 상태를 보여줄 수 있다.

### 회원 탈퇴

`DELETE /users/me` `{ "password": "현재 비밀번호" }`

- 비밀번호가 맞으면 회원 정보와 인증 기록이 **즉시, 완전히 삭제**된다. 되돌릴 수 없으니 화면에서 한 번 더 확인을 받는다.
- 탈퇴 후 기존 토큰은 `INVALID_TOKEN`이 되고, 같은 아이디·이메일로 다시 가입할 수 있다.
- 비밀번호가 틀리면 `WRONG_CURRENT_PASSWORD`가 온다.

비밀번호 변경과 회원 탈퇴에서 현재 비밀번호를 **합쳐서 5번 틀리면 15분 동안** 두 기능 모두 막힌다 (`TOO_MANY_PASSWORD_ATTEMPTS`). 로그인 토큰을 도둑맞았을 때 비밀번호를 계속 맞혀보는 것을 막기 위해서다.

## 정해진 값

| 항목 | 값 |
|---|---|
| `language` | 가입 시 저장하는 사용자 언어: `ko` 한국어, `en` English, `ja` 日本語, `zh-CN` 简体中文, `zh-TW` 繁體中文 (국적은 받지 않음) |
| `lang` | 메일 보내는 API에서 쓰는 메일 언어. 값은 `language`와 같음 (기본값 `ko`) |
| `age_group` | `teens`, `20s`, `30s`, `40s`, `50plus` |
| `skin_type` | `DRY` 건성, `OILY` 지성, `COMBINATION` 복합성, `NORMAL` 중성 |
| `sensitivity` | 피부 민감도. "새 화장품을 쓰면 따갑거나 붉어지나요?" → `NONE` 거의 없음(기본값), `SOMETIMES` 가끔, `OFTEN` 자주. 추천 순위 조정에 쓴다 |
| `avoided_ingredients` 추천값 | 피하고 싶은 성분. 추천에서 제외한다. `fragrance` 향료, `essentialOil` 에센셜 오일, `paraben` 파라벤류, `ethanol` 에탄올, `silicone` 실리콘 |

`avoided_ingredients`에는 "기타"로 직접 입력한 글자도 넣을 수 있다 (항목당 30자, 최대 20개).

## 입력 규칙

- 아이디: 영문과 숫자만 4~20자 (밑줄·띄어쓰기·한글·특수문자 불가). 대소문자를 구분하지 않는다. `Routy01`로 입력해도 `routy01`로 저장되고, 로그인·중복확인·비밀번호 찾기에서도 대소문자 상관없이 같은 아이디로 처리한다.
- 비밀번호: 8~64자, 영문·숫자·특수문자만 사용 가능 (띄어쓰기 불가), 영문·숫자·특수문자를 각각 1자 이상 포함 (대소문자는 상관없음)
- 인증 코드: 숫자 6자리, 10분 동안 유효, 5번 틀리면 다시 요청
- 인증 코드 재요청: 60초 뒤부터 가능

## 개인정보 정리

인증 코드만 요청하고 가입하지 않은 이메일 기록은 만료되면 자동으로 지워진다. 서버가 켜질 때와 인증 코드를 새로 보낼 때 만료된 기록을 정리한다.

## 요청 횟수 제한 (IP 기준)

| 대상 | 제한 |
|---|---|
| 메일 발송 (`/send-verification-email`, `/password-reset/send-code`, `/find-username` 합산) | 10분에 5번, 하루 30번 |
| 인증 코드 확인 (`/verify-email`, `/password-reset/verify-code`, `/password-reset/confirm` 합산) | 10분에 30번 |
| 로그인 | 10분에 30번 |
| 아이디 중복확인 | 10분에 60번 |

넘으면 `RATE_LIMITED`(429)와 함께 `retry_after`(초)가 온다. 숫자는 `app/config.py`에서 바꾼다.

이 제한은 서버 메모리에 기록되기 때문에 서버를 다시 켜면 초기화된다. 지금처럼 서버를 하나만 띄울 때만 정확하게 동작한다. 나중에 Nginx 같은 프록시 뒤에서 서버를 돌리면 모든 요청이 프록시 IP로 보이므로, uvicorn을 `--proxy-headers --forwarded-allow-ips=<프록시 IP>` 옵션으로 실행해야 한다.

## 에러 응답

모든 에러는 아래 형식으로 온다. 화면에 보여줄 문구는 `code`를 보고 프론트에서 언어별로 정한다. `message`는 한국어 참고용이다.

```json
{ "code": "CODE_MISMATCH", "message": "인증 코드가 일치하지 않습니다 (남은 시도 3회)", "remaining_attempts": 3 }
```

| code | 상태 | 의미 | 추가 값 |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | 입력값 규칙 위반 (너무 긴 입력 포함) | `errors: [{field, reason}]` |
| `NOT_FOUND` | 404 | 없는 주소로 요청 | |
| `METHOD_NOT_ALLOWED` | 405 | 잘못된 요청 방식 (예: POST API에 GET) | |
| `USERNAME_TAKEN` | 400 | 이미 있는 아이디 | |
| `EMAIL_TAKEN` | 400 | 이미 가입된 이메일 | |
| `USERNAME_OR_EMAIL_TAKEN` | 400 | 가입 순간 다른 사람이 먼저 가입함 | |
| `EMAIL_NOT_VERIFIED` | 400 | 이메일 인증 안 됨 (또는 인증 후 30분 지남) | |
| `CONSENT_REQUIRED` | 400 | 필수 동의 항목 누락 | `missing` (빠진 항목 목록) |
| `CODE_RESEND_TOO_SOON` | 429 | 60초 안에 재요청 | `retry_after` (초) |
| `VERIFICATION_NOT_FOUND` | 404 | 코드를 요청한 적 없음 | |
| `CODE_EXPIRED` | 400 | 코드 만료 | |
| `CODE_MISMATCH` | 400 | 코드 틀림 | `remaining_attempts` |
| `TOO_MANY_ATTEMPTS` | 429 | 5번 틀림, 코드 폐기 | |
| `INVALID_CREDENTIALS` | 401 | 아이디 또는 비밀번호 틀림 | |
| `TOO_MANY_LOGIN_ATTEMPTS` | 429 | 이 기기에서 5번 실패, 15분 차단 | `retry_after` (초) |
| `ACCOUNT_LOCKED` | 429 | 여러 기기 합쳐 20번 실패, 계정 15분 잠김 | `retry_after` (초) |
| `RATE_LIMITED` | 429 | 같은 IP에서 요청이 너무 많음 | `retry_after` (초) |
| `USER_NOT_FOUND` | 404 | 일치하는 계정 없음 | |
| `INVALID_RESET_TOKEN` | 400 | 재설정 시간 만료 또는 이미 사용함 | |
| `UNAUTHORIZED` | 401 | 토큰 없음 | |
| `INVALID_TOKEN` | 401 | 토큰 만료, 잘못됨, 또는 비밀번호 변경으로 무효 → 다시 로그인 | |
| `WRONG_CURRENT_PASSWORD` | 400 | 현재 비밀번호 틀림 | |
| `TOO_MANY_PASSWORD_ATTEMPTS` | 429 | 비밀번호 변경·탈퇴에서 5번 틀림, 15분 차단 | `retry_after` (초) |
| `SAME_AS_CURRENT_PASSWORD` | 400 | 새 비밀번호가 현재와 같음 | |
