"""Visual/functional verification: fetch registry + unified view with auth."""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"
REQ = "f62e30dc-00fd-4ac4-a9ce-8fa92820b5c3"


def call(method, path, token=None):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


status, tok = call("POST", "/auth/login")
# login needs a body; do it properly
import urllib.request as u
req = u.Request(BASE + "/auth/login", method="POST")
req.add_header("Content-Type", "application/json")
req.data = json.dumps({"email": "lawyer@rasikh.local", "password": "Demo1234!"}).encode()
with u.urlopen(req) as resp:
    token = json.loads(resp.read())["access_token"]

s, reg = call("GET", "/requests/registry?limit=5", token)
print("registry:", s)
for row in reg[:5]:
    r = row["request"]
    print(f"  {r['request_id'][:14]}… type={r['request_type']} answer={row['has_answer']} "
          f"drafts={row['draft_count']} oblig={row['obligation_count']} "
          f"appr={row['approval_count']} find={row['finding_count']} status={r['status']}")

s, view = call("GET", f"/requests/{REQ}/view", token)
print("\nview:", s)
print("  request:", view["request"]["request_id"], view["request"]["request_type"],
      view["request"]["org_id"], view["request"]["status"])
print("  answer:", (view["answer"] or "None")[:80])
print("  counts:", view["counts"])
print("  sources:", [(x["contract_id"], x["title"][:40]) for x in view["sources"]])
print("  obligations sample:", [o["obligation_id"] for o in view["obligations"][:3]])