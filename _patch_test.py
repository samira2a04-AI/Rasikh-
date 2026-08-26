import io

for p in ("tests/test_api.py", "tests/test_workflow.py"):
    s = io.open(p, encoding="utf-8").read()
    anchor = (
        "        for evt in session.scalars(\n"
        "            select(AuditEvent).where(AuditEvent.request_id == request_id)\n"
        "        ):\n"
        "            session.delete(evt)\n"
    )
    assert anchor in s, p
    add = (
        "        for run_row in session.scalars(\n"
        "            select(AnalysisRun).where(AnalysisRun.request_id == request_id)\n"
        "        ):\n"
        "            session.delete(run_row)\n"
    )
    s = s.replace(anchor, anchor + add, 1)
    # Ensure AnalysisRun is imported.
    if "AnalysisRun" not in s.split("def _cleanup_request_chain")[0]:
        assert "from app.models import" in s, p
        s = s.replace(
            "from app.models import (",
            "from app.models import (\n    AnalysisRun,",
            1,
        )
        if "from app.models import (" not in s:
            raise SystemExit(f"no paren import in {p}")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("patched", p)