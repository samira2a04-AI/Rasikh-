# Rasikh — Known Backend Limitations

Deliberate, documented gaps in the current implementation. Each entry states
exactly what is missing, why it was left as-is, and the minimal change that
would close it.

---

## 1. ~~Authenticated user ↔ firm‑team membership is not mapped~~ — RESOLVED

**Status: resolved.** Authenticated users can now be linked to a firm/team
member and the request-intake flow derives the requester automatically.

What was added:
- `users.member_id` nullable FK → `team_member.member_id` (migration
  `d7e4a1b2c35f`, column + relationship on both models).
- `GET /auth/me` returns the authenticated user plus their mapped `member`.
- `POST /requests` accepts an omitted `requester_id` and derives it from
  `users.member_id`, or returns 400 if the account is unmapped.
- `scripts/seed_demo_users.py` ties the demo accounts to `L-01`/`L-02`
  (idempotent; invoked automatically from `scripts/load_data.py`).

Note: `users.member_id` is nullable — a self-registered account with no roster
link can still authenticate, but cannot author a request until mapped.

