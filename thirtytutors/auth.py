"""Accounts for hosted mode (THIRTYTUTORS_HOSTED=1) - invite-only sign-up,
password login and cookie sessions, plus the guard that decides what a request
may reach. The desktop app has none of this: it only ever serves its own
window on 127.0.0.1, so is_hosted() false means every check here is skipped.

The guard is deny-by-default: anything not listed as public needs a session,
and anything under /api/profiles/{id} needs that profile to belong to the user.
Routes that only make sense on the machine in front of the user (opening
folders, self-updating, restarting) don't exist in hosted mode at all. Backup
import stays off too, because a backup can replace a profile by id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from . import memory
from .profiles_store import get_profile_by_id

SESSION_COOKIE = "tt_session"
SESSION_LIFETIME_S = 30 * 24 * 3600
MIN_PASSWORD_LENGTH = 10
MAX_REQUEST_BYTES = 25 * 1024 * 1024  # generous for voice enrollment clips

LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_S = 15 * 60

_SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024}

_PUBLIC_EXACT = {
    "/login",
    "/api/auth/login",
    "/api/auth/register",
    "/favicon.ico",
    "/ThirtyTutors.ico",
    "/UI/scripts/login.js",
    "/UI/scripts/theme.js",
}
_PUBLIC_PREFIXES = ("/UI/styles/",)
_DISABLED_EXACT = {
    "/api/open-data-folder",
    "/api/open-backups-folder",
    "/api/update-app",
    "/api/update-assets",
    "/api/update-marketing-assets",
    "/api/restart-app",
    "/api/profiles/import",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/game-test-scene",
    "/game-test-room-inspect",
}
_DISABLED_PREFIXES = ("/game_test/", "/game-test/")
_PROFILE_PATH = re.compile(r"^/api/profiles/([^/]+)(?:/|$)")

router = APIRouter()


class AuthError(Exception):
    """A sign-up or login problem whose message is safe to show the user."""


def is_hosted() -> bool:
    return os.environ.get("THIRTYTUTORS_HOSTED") == "1"


# --- Secrets at rest ---


def _fernet() -> Fernet:
    secret = os.environ.get("THIRTYTUTORS_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("Hosted mode needs THIRTYTUTORS_SECRET_KEY set to at least 32 characters.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt_secret(value: str) -> str:
    return "enc:" + _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value.startswith("enc:"):
        return value
    return _fernet().decrypt(value[4:].encode()).decode()


# --- Passwords and tokens ---


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}:{derived.hex()}"


def _password_matches(password: str, stored: str) -> bool:
    salt_hex = stored.split(":", 1)[0]
    return hmac.compare_digest(_hash_password(password, bytes.fromhex(salt_hex)), stored)


# Compared against when the email is unknown, so a login takes the same time
# whether or not the account exists.
_DUMMY_PASSWORD_HASH = _hash_password(secrets.token_urlsafe(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Invites, users, sessions ---


def create_invite() -> str:
    code = secrets.token_urlsafe(16)
    conn = memory._connect()
    try:
        conn.execute("INSERT INTO invites (code_hash, created_ts) VALUES (?,?)", (_token_hash(code), int(time.time())))
        conn.commit()
    finally:
        conn.close()
    return code


def register_user(invite_code: str, email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise AuthError("Enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.")
    password_hash = _hash_password(password)
    user_id = str(uuid.uuid4())
    now = int(time.time())
    conn = memory._connect()
    try:
        claimed = conn.execute(
            "UPDATE invites SET used_by=?, used_ts=? WHERE code_hash=? AND used_by IS NULL",
            (user_id, now, _token_hash(invite_code or "")),
        )
        if claimed.rowcount != 1:
            conn.rollback()
            raise AuthError("This invite code isn't valid or has already been used.")
        try:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, created_ts) VALUES (?,?,?,?)",
                (user_id, email, password_hash, now),
            )
        except sqlite3.IntegrityError:
            conn.rollback()  # the invite stays usable
            raise AuthError("An account with this email already exists.") from None
        conn.commit()
    finally:
        conn.close()
    return {"id": user_id, "email": email}


def verify_login(email: str, password: str) -> dict | None:
    email = (email or "").strip().lower()
    conn = memory._connect()
    try:
        row = conn.execute("SELECT id, email, password_hash FROM users WHERE email=?", (email,)).fetchone()
    finally:
        conn.close()
    if row is None:
        _password_matches(password or "", _DUMMY_PASSWORD_HASH)
        return None
    if not _password_matches(password or "", row["password_hash"]):
        return None
    return {"id": row["id"], "email": row["email"]}


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn = memory._connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE expires_ts<?", (now,))
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_ts) VALUES (?,?,?)",
            (_token_hash(token), user_id, now + SESSION_LIFETIME_S),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    conn = memory._connect()
    try:
        row = conn.execute(
            "SELECT users.id, users.email FROM auth_sessions JOIN users ON users.id=auth_sessions.user_id "
            "WHERE token_hash=? AND expires_ts>=?",
            (_token_hash(token), int(time.time())),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    conn = memory._connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))
        conn.commit()
    finally:
        conn.close()


# --- Login rate limit (in memory: a restart clearing it is acceptable) ---

_login_failures: dict[str, list[float]] = defaultdict(list)


def _too_many_failures(key: str) -> bool:
    cutoff = time.time() - LOGIN_WINDOW_S
    _login_failures[key] = [t for t in _login_failures[key] if t > cutoff]
    return len(_login_failures[key]) >= LOGIN_MAX_FAILURES


def _rate_limit_key(request: Request, kind: str) -> str:
    return f"{kind}:{request.client.host if request.client else 'unknown'}"


# --- Access rules ---


def user_owns_profile(user: dict | None, profile: dict | None) -> bool:
    return bool(user and profile and profile.get("owner_id") == user["id"])


def _origin_allowed(origin: str | None, host: str | None) -> bool:
    # Non-browser clients send no Origin, and have no cookie to ride on anyway.
    return not origin or urlparse(origin).netloc == host


def _is_public(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)


def _is_disabled(path: str) -> bool:
    return path in _DISABLED_EXACT or path.startswith(_DISABLED_PREFIXES)


async def hosted_guard(request: Request, call_next):
    if not is_hosted():
        return await call_next(request)

    path = request.url.path
    if _is_disabled(path):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    content_length = request.headers.get("content-length", "0")
    if content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _origin_allowed(
        request.headers.get("origin"), request.headers.get("host")
    ):
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    if _is_public(path):
        return await call_next(request)

    user = user_for_token(request.cookies.get(SESSION_COOKIE))
    if user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Log in first"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    request.state.user = user

    match = _PROFILE_PATH.match(path)
    if match and not user_owns_profile(user, get_profile_by_id(match.group(1))):
        # 404, not 403 - someone else's profile looks the same as no profile.
        return JSONResponse({"detail": "Profile not found"}, status_code=404)
    return await call_next(request)


def websocket_user(websocket) -> dict | None:
    if not _origin_allowed(websocket.headers.get("origin"), websocket.headers.get("host")):
        return None
    return user_for_token(websocket.cookies.get(SESSION_COOKIE))


# --- Routes ---


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_LIFETIME_S,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.post("/api/auth/register")
async def register(request: Request, response: Response):
    key = _rate_limit_key(request, "register")
    if _too_many_failures(key):
        raise HTTPException(429, "Too many attempts - try again later.")
    payload = await request.json()
    try:
        user = register_user(payload.get("invite_code"), payload.get("email"), payload.get("password"))
    except AuthError as e:
        _login_failures[key].append(time.time())
        raise HTTPException(400, str(e)) from None
    _set_session_cookie(response, create_session(user["id"]))
    return {"email": user["email"]}


@router.post("/api/auth/login")
async def login(request: Request, response: Response):
    key = _rate_limit_key(request, "login")
    if _too_many_failures(key):
        raise HTTPException(429, "Too many attempts - try again later.")
    payload = await request.json()
    user = verify_login(payload.get("email"), payload.get("password"))
    if user is None:
        _login_failures[key].append(time.time())
        # The same message whether or not the account exists, so it can't be
        # used to find out who has one.
        raise HTTPException(401, "Wrong email or password. New here? You need an invite code to create an account.")
    _login_failures.pop(key, None)
    _set_session_cookie(response, create_session(user["id"]))
    return {"email": user["email"]}


@router.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"logged_out": True}


@router.get("/api/auth/me")
async def me(request: Request):
    user = getattr(request.state, "user", None)
    return {"hosted": is_hosted(), "email": user["email"] if user else None}
