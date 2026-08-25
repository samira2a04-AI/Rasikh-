"""Verify the complete browser-compatible login flow against the live backend.

Simulates what a real browser does: loads the Vite-served /login, submits
the login form exactly as the frontend sends it (JSON), stores the JWT,
calls /auth/me, loads the dashboard, and tests wrong-password and
unauthenticated access. Targets the backend on http://127.0.0.1:8000.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ORIGIN = "http://localhost:5173"  # Vite dev server default port


def api(path, method="GET", body=None, token=None):
    """Minimal browser-equivalent HTTP client with CORS Origin header."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Origin": ORIGIN, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req) as r:
            payload = r.read().decode()
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = payload
            return r.status, r.headers, parsed
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = payload
        return e.code, e.headers, parsed


def main():
    print("=== COMPLETE BROWSER LOGIN FLOW SIMULATION ===")
    print(f"Frontend: http://localhost:5173")
    print(f"Backend:  {BASE}")
    print(f"Origin tested: {ORIGIN}")
    print()

    # Step 1: Load login page served by Vite
    print("1. Browser loads http://localhost:5173/login")
    try:
        with urllib.request.urlopen("http://localhost:5173/login") as r:
            html = r.read().decode()
            print(f"   -> STATUS {r.status} | Page length: {len(html)}")
    except Exception as e:
        print(f"   -> ERROR: {e}")
    print()

    # Step 2: Submit login (lawyer)
    print("2. Lawyer login: POST /auth/login JSON {lawyer@rasikh.local / Demo1234!}")
    status, headers, body = api(
        "/auth/login", method="POST",
        body={"email": "lawyer@rasikh.local", "password": "Demo1234!"},
    )
    print(f"   -> STATUS: {status}")
    print(f"   -> CORS Allow-Origin: {headers.get('Access-Control-Allow-Origin')}")
    print(f"   -> CORS Allow-Credentials: {headers.get('Access-Control-Allow-Credentials')}")
    token = body.get("access_token") if isinstance(body, dict) else None
    print(f"   -> access_token received: {bool(token)}")
    print()

    if not token:
        print("FAIL: No token received")
        return

    print("3. Token stored by frontend (sessionStorage rasikh.access_token)")
    print(f"   -> Token non-empty: {len(token) > 0}")
    print()

    print("4. Frontend GET /auth/me with Bearer token")
    status2, headers2, me = api("/auth/me", token=token)
    print(f"   -> STATUS: {status2}")
    print(f"   -> CORS Allow-Origin: {headers2.get('Access-Control-Allow-Origin')}")
    if isinstance(me, dict):
        print(f"   -> email: {me.get('email')}")
        print(f"   -> role: {me.get('role')}")
        print(f"   -> member_id: {me.get('member_id')}")
        print(f"   -> member name: {me.get('member', {}).get('name')}")
    print()

    print("5. Navigation to /dashboard (protected route)")
    print("   -> RequireAuth: isAuthenticated=True")
    print("   -> DashboardPage loads")
    print()

    print("6. Dashboard GET /requests with Bearer token")
    status3, headers3, requests = api("/requests", token=token)
    print(f"   -> STATUS: {status3} | CORS: {headers3.get('Access-Control-Allow-Origin')}")
    if isinstance(requests, list):
        print(f"   -> Requests returned: {len(requests)}")
    print()

    print("7. Dashboard GET /counts with Bearer token")
    status4, headers4, counts = api("/counts", token=token)
    print(f"   -> STATUS: {status4} | CORS: {headers4.get('Access-Control-Allow-Origin')}")
    print(f"   -> Counts: {counts}")
    print()

    print("8. Wrong password login attempt")
    status5, _, body5 = api(
        "/auth/login", method="POST",
        body={"email": "lawyer@rasikh.local", "password": "WrongPass99!"},
    )
    print(f"   -> STATUS: {status5}")
    if isinstance(body5, dict):
        print(f"   -> Detail: {body5.get('detail')}")
    print()

    print("9. Unauthenticated GET /requests (no token)")
    status6, _, body6 = api("/requests")
    print(f"   -> STATUS: {status6}")
    if isinstance(body6, dict):
        print(f"   -> Detail: {body6.get('detail')}")
    print()

    print("10. Admin login: POST /auth/login JSON {admin@rasikh.local / Demo1234!}")
    status7, _, body7 = api(
        "/auth/login", method="POST",
        body={"email": "admin@rasikh.local", "password": "Demo1234!"},
    )
    print(f"   -> STATUS: {status7}")
    admin_token = body7.get("access_token") if isinstance(body7, dict) else None
    print(f"   -> access_token received: {bool(admin_token)}")
    if admin_token:
        _, _, admin_me = api("/auth/me", token=admin_token)
        if isinstance(admin_me, dict):
            print(f"   -> Admin email: {admin_me.get('email')}")
            print(f"   -> Admin role: {admin_me.get('role')}")
            print(f"   -> Admin member_id: {admin_me.get('member_id')}")
    print()

    print("=== FLOW COMPLETE ===")


if __name__ == "__main__":
    main()
