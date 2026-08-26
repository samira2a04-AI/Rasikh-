import json
from pathlib import Path

ak = json.loads(Path("data/answer_key.json").read_text(encoding="utf-8"))
for req_id, data in ak.items():
    print(f"{req_id}: decision={data.get('decision')} org={data.get('org')} access={data.get('access')}")
