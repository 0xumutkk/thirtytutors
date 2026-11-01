"""Hosted mode's access rules (auth.py) - accounts, one user never reaching
another's data, and the Gemini key never leaving the server. Uses the real
app rather than a bare router, because the guard is middleware on it.
"""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from thirtytutors import auth, memory, profiles_store, quizzes
from thirtytutors.main import app

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def hosted(monkeypatch):
    monkeypatch.setenv("THIRTYTUTORS_HOSTED", "1")
    monkeypatch.setenv("THIRTYTUTORS_SECRET_KEY", "x" * 40)
    auth._login_failures.clear()


def _client():
    # https: the session cookie is Secure.
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def _signed_up(email="a@example.com"):
    client = _client()
    res = client.post(
        "/api/auth/register",
        json={"invite_code": auth.create_invite(), "email": email, "password": PASSWORD},
    )
    assert res.status_code == 200
    auth._login_failures.clear()
    return client


def _profile_of(client, api_key="AIza-secret-key"):
    return client.post("/api/profiles", json={"name": "Me", "api_key": api_key}).json()


# --- Everything is closed without a session ---


@pytest.mark.parametrize("path", ["/api/profiles", "/api/voices", "/api/auth/me", "/api/scenarios"])
def test_api_needs_a_session(path):
    assert _client().get(path).status_code == 401


@pytest.mark.parametrize("path", ["/", "/home", "/profiles", "/UI/pages/home.html", "/photos/Kore.webp"])
def test_pages_and_assets_redirect_to_login(path):
    res = _client().get(path)
    assert res.status_code == 303
    assert res.headers["location"] == "/login"


def test_login_page_is_public():
    assert _client().get("/login").status_code == 200
    assert _client().get("/UI/scripts/login.js").status_code == 200


# --- Invites and accounts ---


def test_sign_up_needs_a_valid_invite():
    res = _client().post("/api/auth/register", json={"invite_code": "nope", "email": "a@example.com", "password": PASSWORD})
    assert res.status_code == 400


def test_invite_works_only_once():
    code = auth.create_invite()
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "a@example.com", "password": PASSWORD})
        .status_code
        == 200
    )
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "b@example.com", "password": PASSWORD})
        .status_code
        == 400
    )


def test_duplicate_email_keeps_the_invite_usable():
    _signed_up("a@example.com")
    code = auth.create_invite()
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "A@example.com", "password": PASSWORD})
        .status_code
        == 400
    )
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "b@example.com", "password": PASSWORD})
        .status_code
        == 200
    )


def test_short_password_is_refused_without_using_the_invite():
    code = auth.create_invite()
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "a@example.com", "password": "short"})
        .status_code
        == 400
    )
    assert (
        _client()
        .post("/api/auth/register", json={"invite_code": code, "email": "a@example.com", "password": PASSWORD})
        .status_code
        == 200
    )


def test_session_cookie_is_locked_down():
    client = _client()
    res = client.post(
        "/api/auth/register", json={"invite_code": auth.create_invite(), "email": "a@example.com", "password": PASSWORD}
    )
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie


def test_login_and_logout():
    _signed_up()
    client = _client()
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").json()["email"] == "a@example.com"
    client.post("/api/auth/logout")
    assert client.get("/api/profiles").status_code == 401


def test_logout_kills_the_session_on_the_server():
    client = _signed_up()
    token = client.cookies.get(auth.SESSION_COOKIE)
    client.post("/api/auth/logout")
    assert auth.user_for_token(token) is None


def test_repeated_login_failures_are_blocked():
    _signed_up()
    client = _client()
    for _ in range(auth.LOGIN_MAX_FAILURES):
        client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong password"})
    res = client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert res.status_code == 429


# --- One user can't reach another's data ---


def test_profile_list_only_shows_your_own():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    mine = _profile_of(a)
    _profile_of(b)
    assert [p["id"] for p in a.get("/api/profiles").json()["profiles"]] == [mine["id"]]


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("get", ""),
        ("put", ""),
        ("delete", ""),
        ("get", "/export"),
        ("get", "/stats"),
        ("get", "/mic-status"),
        ("get", "/conversations"),
        ("post", "/conversations"),
        ("put", "/active-conversation"),
        ("post", "/check-auto-backup"),
    ],
)
def test_other_users_profile_looks_missing(method, suffix):
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    profile = _profile_of(a)
    kwargs = {"json": {}} if method in ("put", "post") else {}
    res = getattr(b, method)(f"/api/profiles/{profile['id']}{suffix}", **kwargs)
    assert res.status_code == 404
    assert profiles_store.get_profile_by_id(profile["id"]) is not None


def test_other_users_conversation_is_unreachable():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    profile = _profile_of(a)
    conv = a.post(f"/api/profiles/{profile['id']}/conversations", json={"target_language": "English"}).json()
    b_profile = _profile_of(b)
    assert b.get(f"/api/profiles/{b_profile['id']}/conversations/{conv['id']}").status_code == 404
    assert b.get(f"/api/profiles/{profile['id']}/conversations/{conv['id']}").status_code == 404


def test_quiz_id_from_another_conversation_is_refused():
    a = _signed_up()
    profile = _profile_of(a)
    conv_a = a.post(f"/api/profiles/{profile['id']}/conversations", json={"target_language": "English"}).json()
    conv_b = a.post(f"/api/profiles/{profile['id']}/conversations", json={"target_language": "Polish"}).json()
    quiz_id = quizzes.start_quiz_session(conv_b["id"], "review", {"items": []})
    res = a.post(f"/api/profiles/{profile['id']}/conversations/{conv_a['id']}/reviewable-quiz/{quiz_id}/finish?status=skipped")
    assert res.status_code == 404


def test_owner_cant_be_reassigned():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    profile = _profile_of(a)
    a.put(f"/api/profiles/{profile['id']}", json={"owner_id": "someone-else"})
    assert b.get(f"/api/profiles/{profile['id']}").status_code == 404
    assert a.get(f"/api/profiles/{profile['id']}").status_code == 200


# --- The Gemini key stays on the server ---


def test_key_is_never_in_a_response():
    a = _signed_up()
    created = _profile_of(a)
    url = f"/api/profiles/{created['id']}"
    for res in (a.get(url), a.put(url, json={"name": "New"}), a.put(url, json={"api_key": "AIza-other-key"})):
        assert "AIza" not in res.text
        assert "api_key" not in res.json()
        assert res.json()["has_api_key"] is True
    assert "AIza" not in json.dumps(created)
    assert "owner_id" not in created


def test_key_is_encrypted_on_disk_and_usable_in_memory():
    a = _signed_up()
    created = _profile_of(a)
    on_disk = profiles_store.PROFILES_FILE.read_text()
    assert "AIza-secret-key" not in on_disk
    assert "enc:" in on_disk
    assert profiles_store.get_profile_by_id(created["id"])["api_key"] == "AIza-secret-key"


def test_backup_doesnt_contain_the_key():
    import io
    import zipfile

    a = _signed_up()
    created = _profile_of(a)
    res = a.get(f"/api/profiles/{created['id']}/export")
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        manifest = zf.read("manifest.json").decode()
    assert "AIza" not in manifest
    assert "enc:" not in manifest


def test_missing_secret_key_refuses_to_store_keys(monkeypatch):
    monkeypatch.delenv("THIRTYTUTORS_SECRET_KEY")
    with pytest.raises(RuntimeError):
        auth.encrypt_secret("x")


# --- Local-machine features don't exist here ---


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/open-data-folder"),
        ("post", "/api/update-app"),
        ("post", "/api/update-assets"),
        ("post", "/api/restart-app"),
        ("post", "/api/profiles/import"),
        ("get", "/docs"),
        ("get", "/openapi.json"),
    ],
)
def test_local_only_routes_are_gone(method, path):
    assert getattr(_signed_up(), method)(path).status_code == 404


def test_no_updates_are_ever_offered():
    status = _signed_up().get("/api/update-status").json()
    assert not any(part["update_available"] for part in status.values())


def test_cross_site_post_is_refused():
    a = _signed_up()
    res = a.post("/api/profiles", json={"name": "X"}, headers={"origin": "https://evil.example"})
    assert res.status_code == 403


def test_same_site_post_is_allowed():
    a = _signed_up()
    res = a.post("/api/profiles", json={"name": "X"}, headers={"origin": "https://testserver"})
    assert res.status_code == 200


# --- Live session socket ---


def test_socket_needs_a_session():
    with pytest.raises(WebSocketDisconnect):
        with _client().websocket_connect("/ws/session"):
            pass


def _socket_headers(client, **extra):
    # The test client's socket URL is ws://, so it won't attach a Secure cookie.
    return {"cookie": f"{auth.SESSION_COOKIE}={client.cookies.get(auth.SESSION_COOKIE)}", **extra}


def test_socket_refuses_another_origin():
    a = _signed_up()
    headers = _socket_headers(a, origin="https://evil.example")
    with pytest.raises(WebSocketDisconnect):
        with a.websocket_connect("/ws/session", headers=headers):
            pass


def test_socket_refuses_someone_elses_profile():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    profile = _profile_of(a)
    with b.websocket_connect("/ws/session", headers=_socket_headers(b)) as ws:
        ws.send_json({"type": "init", "profile_id": profile["id"]})
        assert ws.receive_json() == {"type": "error", "message": "Profile not found."}


def test_socket_refuses_a_session_without_a_profile():
    # The desktop app's first-run fallback takes a key straight from this message.
    a = _signed_up()
    with a.websocket_connect("/ws/session", headers=_socket_headers(a)) as ws:
        ws.send_json({"type": "init", "api_key": "AIza-whatever"})
        assert ws.receive_json() == {"type": "error", "message": "Profile not found."}


def test_socket_lets_the_owner_past_the_check():
    a = _signed_up()
    profile = _profile_of(a)
    with a.websocket_connect("/ws/session", headers=_socket_headers(a)) as ws:
        ws.send_json({"type": "init", "profile_id": profile["id"]})
        # No conversation yet, so it stops at the next check - not the ownership one.
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["message"] != "Profile not found."


# --- Desktop mode is unaffected ---


def test_desktop_mode_stays_open_and_plain(monkeypatch):
    monkeypatch.delenv("THIRTYTUTORS_HOSTED")
    client = TestClient(app)
    created = client.post("/api/profiles", json={"name": "Me", "api_key": "AIza-desktop"}).json()
    assert client.get("/api/profiles").status_code == 200
    assert "api_key" not in created
    assert created["has_api_key"] is True
    assert "AIza-desktop" in profiles_store.PROFILES_FILE.read_text()
    assert memory.get_turn_count("nothing") == 0


# --- Caching ---


def test_downloaded_assets_are_cacheable_but_pages_arent():
    a = _signed_up()
    asset_dir = auth_assets_dir()
    (asset_dir / "avatar").mkdir(parents=True, exist_ok=True)
    (asset_dir / "avatar" / "cache_test.glb").write_bytes(b"glb")
    try:
        assert "max-age" in a.get("/avatar/cache_test.glb").headers["cache-control"]
        assert "no-store" in a.get("/home").headers["cache-control"]
    finally:
        (asset_dir / "avatar" / "cache_test.glb").unlink()


def auth_assets_dir():
    from thirtytutors.main import ASSETS_DIR

    return ASSETS_DIR


def test_failed_login_reads_the_same_with_or_without_an_account():
    _signed_up("a@example.com")
    client = _client()
    known = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong password"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong password"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()
    assert "invite code" in known.json()["detail"]


# --- No 3D avatars on the web ---


def test_lesson_page_has_no_3d_code_or_camera_button():
    html = _signed_up().get("/").text
    assert "avatarDrawer.js" not in html
    assert "talkinghead" not in html
    assert "cameraToggleBtn" not in html
    assert "talkBtn" in html


def test_selection_page_is_told_not_to_load_3d():
    assert "window.TT_NO_3D = true" in _signed_up().get("/avatar-select").text


def test_tutors_are_available_from_photos_alone(isolated_data_dir, monkeypatch):
    from thirtytutors import routes_api

    photos = isolated_data_dir / "assets" / "photos"
    photos.mkdir(parents=True)
    (photos / "Kore.webp").write_bytes(b"x")
    monkeypatch.setattr(routes_api, "ASSETS_DIR", isolated_data_dir / "assets")
    assert _signed_up().get("/api/avatars").json()["available"] == ["Kore"]


def test_tutor_has_no_mood_tool_or_rules():
    from thirtytutors import live_session

    config = live_session.build_config(
        {"id": "p", "name": "Alex", "api_key": "k"},
        {"target_language": "English", "native_language": "Turkish", "scenario": "speaking_coach"},
        "gemini-2.5-flash-native-audio-latest",
    )
    names = {fn.name for tool in config.tools for fn in tool.function_declarations}
    assert names == {"start_quiz", "log_mistake"}
    text = (
        config.system_instruction
        if isinstance(config.system_instruction, str)
        else "".join(p.text or "" for p in config.system_instruction.parts)
    )
    assert "set_mood" not in text
    assert "Quiz on real mistakes" in text
    assert "trouble spot" in text


# --- Saved words ---


def test_saved_words_api_round_trip():
    a = _signed_up()
    url = f"/api/profiles/{_profile_of(a)['id']}/saved-words"
    saved = a.post(url, json={"term": " earn money ", "context": "You earn money."}).json()
    assert saved["term"] == "earn money"
    assert [w["term"] for w in a.get(url).json()["words"]] == ["earn money"]
    assert a.delete(f"{url}/{saved['id']}").status_code == 200
    assert a.get(url).json()["words"] == []


@pytest.mark.parametrize("term", ["", "   ", "x" * 121])
def test_saved_word_must_be_a_short_phrase(term):
    a = _signed_up()
    assert a.post(f"/api/profiles/{_profile_of(a)['id']}/saved-words", json={"term": term}).status_code == 400


def test_other_users_saved_words_are_unreachable():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    url = f"/api/profiles/{_profile_of(a)['id']}/saved-words"
    saved = a.post(url, json={"term": "earn money"}).json()
    assert b.get(url).status_code == 404
    assert b.post(url, json={"term": "x"}).status_code == 404
    assert b.delete(f"{url}/{saved['id']}").status_code == 404


def test_saved_word_ignores_a_conversation_of_someone_else():
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    a_profile = _profile_of(a)
    conv = a.post(f"/api/profiles/{a_profile['id']}/conversations", json={"target_language": "English"}).json()
    saved = b.post(f"/api/profiles/{_profile_of(b)['id']}/saved-words", json={"term": "x", "conversation_id": conv["id"]}).json()
    assert saved["conversation_id"] is None


# --- Word meanings ---


def _conversation(client, profile, **config):
    return client.post(f"/api/profiles/{profile['id']}/conversations", json={"target_language": "English", **config}).json()


def _capture_explain(monkeypatch):
    from thirtytutors import word_help

    calls = {}

    def fake(api_key, term, context, language):
        calls.update(api_key=api_key, term=term, context=context, language=language)
        return "a short meaning"

    monkeypatch.setattr(word_help, "explain_word", fake)
    return calls


def test_meaning_uses_native_language_by_default(monkeypatch):
    calls = _capture_explain(monkeypatch)
    a = _signed_up()
    profile = _profile_of(a)
    conv = _conversation(a, profile, native_language="Turkish")
    res = a.post(
        f"/api/profiles/{profile['id']}/word-meaning", json={"term": "reluctant", "context": "s", "conversation_id": conv["id"]}
    )
    assert res.json() == {"meaning": "a short meaning"}
    assert calls["language"] == "Turkish"
    assert calls["api_key"] == "AIza-secret-key"


def test_meaning_stays_in_the_learned_language_for_target_only_lessons(monkeypatch):
    calls = _capture_explain(monkeypatch)
    a = _signed_up()
    profile = _profile_of(a)
    conv = _conversation(a, profile, native_language="Turkish", explanation_mode="target_only")
    a.post(f"/api/profiles/{profile['id']}/word-meaning", json={"term": "reluctant", "conversation_id": conv["id"]})
    assert calls["language"] == "English"


def test_meaning_refuses_someone_elses_conversation(monkeypatch):
    calls = _capture_explain(monkeypatch)
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    conv = _conversation(a, _profile_of(a))
    res = b.post(f"/api/profiles/{_profile_of(b)['id']}/word-meaning", json={"term": "x", "conversation_id": conv["id"]})
    assert res.status_code == 404
    assert calls == {}


def test_review_quiz_includes_saved_words():
    a = _signed_up()
    profile = _profile_of(a)
    conv = _conversation(a, profile)
    url = f"/api/profiles/{profile['id']}/saved-words"
    a.post(url, json={"term": "reluctant", "context": "She was reluctant to go.", "meaning": "unwilling"})
    a.post(url, json={"term": "earn money"})
    assert a.get(url).json()["words"][1]["meaning"] == "unwilling"
    items = a.get(f"/api/profiles/{profile['id']}/conversations/{conv['id']}/reviewable-quiz").json()["items"]
    assert "reluctant" in [i["target_term"] for i in items]


# --- Reading aloud in the tutor's voice ---


def _capture_speech(monkeypatch):
    from thirtytutors import word_help

    calls = {}

    def fake(api_key, text, voice_name):
        calls.update(api_key=api_key, text=text, voice=voice_name)
        return "QUJD"

    monkeypatch.setattr(word_help, "speak_text", fake)
    return calls


def test_speech_uses_the_conversations_tutor_voice(monkeypatch):
    calls = _capture_speech(monkeypatch)
    a = _signed_up()
    profile = _profile_of(a)
    conv = _conversation(a, profile, voice_name="Puck")
    res = a.post(f"/api/profiles/{profile['id']}/conversations/{conv['id']}/speak", json={"text": "Hello there"})
    assert res.json() == {"audio": "QUJD"}
    assert calls == {"api_key": "AIza-secret-key", "text": "Hello there", "voice": "Puck"}


@pytest.mark.parametrize("text", ["", "x" * 2001])
def test_speech_rejects_empty_or_oversized_text(monkeypatch, text):
    calls = _capture_speech(monkeypatch)
    a = _signed_up()
    profile = _profile_of(a)
    conv = _conversation(a, profile)
    assert a.post(f"/api/profiles/{profile['id']}/conversations/{conv['id']}/speak", json={"text": text}).status_code == 400
    assert calls == {}


def test_speech_refuses_someone_elses_conversation(monkeypatch):
    calls = _capture_speech(monkeypatch)
    a, b = _signed_up("a@example.com"), _signed_up("b@example.com")
    profile = _profile_of(a)
    conv = _conversation(a, profile)
    assert b.post(f"/api/profiles/{profile['id']}/conversations/{conv['id']}/speak", json={"text": "x"}).status_code == 404
    assert b.post(f"/api/profiles/{_profile_of(b)['id']}/conversations/{conv['id']}/speak", json={"text": "x"}).status_code == 404
    assert calls == {}


@pytest.mark.parametrize(
    "path",
    ["/manifest.webmanifest", "/sw.js", "/offline.html", "/UI/icons/icon-192.png", "/UI/icons/icon-512.png"],
)
def test_installable_app_files_are_public(path):
    assert _client().get(path).status_code == 200


def test_pages_link_the_manifest_in_hosted_mode_only(monkeypatch):
    assert 'rel="manifest"' in _client().get("/login").text
    monkeypatch.delenv("THIRTYTUTORS_HOSTED")
    assert 'rel="manifest"' not in _client().get("/login").text
