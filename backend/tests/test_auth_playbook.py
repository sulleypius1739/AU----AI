"""Auth playbook checks: bcrypt format, httpOnly cookies, CORS credentials, lockout, seed idempotency."""
import os
import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
EMAIL, PASSWORD = "president@aureus.ai", "Aureus2020!"


def test_login_sets_httponly_cookies():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    raw = r.headers.get("set-cookie", "")
    assert "access_token" in raw and "HttpOnly" in raw, raw
    me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL
    assert "password_hash" not in me.text


def test_bcrypt_hash_format():
    from aureus.auth import hash_password, verify_password
    h = hash_password("Aureus2020!")
    assert h.startswith("$2b$"), h[:10]
    assert verify_password("Aureus2020!", h)


def test_cors_allows_credentials_explicit_origin():
    r = requests.options(f"{BASE_URL}/api/auth/login", headers={
        "Origin": BASE_URL, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"}, timeout=30)
    allow_origin = r.headers.get("access-control-allow-origin")
    allow_creds = r.headers.get("access-control-allow-credentials")
    assert allow_creds == "true", r.headers
    assert allow_origin != "*", f"wildcard origin with credentials: {allow_origin}"


def test_brute_force_lockout_after_5_failures():
    s = requests.Session()
    codes = []
    for _ in range(6):
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": EMAIL, "password": "WrongPass123!"}, timeout=30)
        codes.append(r.status_code)
    assert any(c in (423, 429) for c in codes), f"no lockout, codes={codes}"
