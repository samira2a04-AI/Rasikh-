"""Validate the Rasikh SQLAlchemy models against docs/data-schema.md.

Checks performed (no database connection required):
1. ``Base`` and all 16 model modules import successfully.
2. All expected tables appear in ``Base.metadata.tables`` (exactly 16).
3. All foreign keys resolve to existing tables/columns (via sorted_tables).
4. All relationships configure without errors (via configure_mappers).
5. The documented indexes, unique constraints, and CHECK constraints exist.

Run from the repository root:  python scripts/validate_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the repository root importable regardless of where this is run from.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401 — importing registers every model with Base.metadata
from app.database.base import Base

EXPECTED_TABLES = {
    "team_member",
    "organisation",
    "matter_assignment",
    "contract",
    "contract_clause",
    "data_room_file",
    "review_standard_clause",
    "request",
    "access_decision",
    "finding",
    "citation",
    "obligation",
    "escalation",
    "draft",
    "approval_decision",
    "audit_event",
}

# table -> set of (column, referenced_table) foreign keys required by the schema
EXPECTED_FKS = {
    "matter_assignment": {("member_id", "team_member"), ("org_id", "organisation")},
    "contract": {("org_id", "organisation")},
    "contract_clause": {("contract_id", "contract")},
    "data_room_file": {("org_id", "organisation")},
    "request": {("requester_id", "team_member"), ("org_id", "organisation")},
    "access_decision": {
        ("request_id", "request"),
        ("member_id", "team_member"),
        ("org_id", "organisation"),
    },
    "finding": {("request_id", "request")},
    "citation": {
        ("finding_id", "finding"),
        ("contract_clause_id", "contract_clause"),
        ("standard_clause_id", "review_standard_clause"),
    },
    "obligation": {("org_id", "organisation"), ("owner_id", "team_member")},
    "escalation": {
        ("request_id", "request"),
        ("obligation_id", "obligation"),
        ("routed_to_id", "team_member"),
    },
    "draft": {("request_id", "request")},
    "approval_decision": {("draft_id", "draft"), ("reviewer_id", "team_member")},
    "audit_event": {("request_id", "request"), ("actor_id", "team_member")},
}

EXPECTED_INDEXES = {
    # matter_assignment's access-lookup index is provided by its unique constraint
    "access_decision": {"ix_access_decision_request_id", "ix_access_decision_member_org_decided_at"},
    "finding": {"ix_finding_request_id"},
    "citation": {"ix_citation_finding_id"},
    "obligation": {"ix_obligation_org_due_date", "ix_obligation_band"},
    "draft": {"ix_draft_request_approval_state"},
    "approval_decision": {"ix_approval_decision_draft_id"},
    "audit_event": {
        "ix_audit_event_request_occurred_at",
        "ix_audit_event_event_type_occurred_at",
    },
    "contract": {"ix_contract_org_id"},
    "data_room_file": {"ix_data_room_file_org_id"},
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "matter_assignment": {"uq_matter_assignment_member_org"},
    "review_standard_clause": {"uq_review_standard_clause_clause_number"},
}

EXPECTED_CHECK_CONSTRAINTS = {
    "team_member": {"ck_team_member_role"},
    "organisation": {"ck_organisation_status"},
    "contract": {"ck_contract_language"},
    "request": {"ck_request_status"},
    "access_decision": {"ck_access_decision_outcome"},
    "citation": {"ck_citation_source_type", "ck_citation_exactly_one_source"},
    "escalation": {"ck_escalation_reason", "ck_escalation_exactly_one_target"},
    "draft": {"ck_draft_approval_state"},
    "approval_decision": {"ck_approval_decision_decision"},
}


def main() -> int:
    failures: list[str] = []

    # 1–2. Tables registered with Base.metadata
    tables = dict(Base.metadata.tables)
    missing = EXPECTED_TABLES - set(tables)
    unexpected = set(tables) - EXPECTED_TABLES
    if missing or unexpected or len(tables) != len(EXPECTED_TABLES):
        failures.append(
            f"table mismatch: missing={sorted(missing)} "
            f"unexpected={sorted(unexpected)} count={len(tables)}"
        )
    else:
        print(f"[OK] {len(tables)} tables registered: {', '.join(sorted(tables))}")

    # 3. Foreign keys resolve (raises NoSuchTableError/NoReferencedColumnError on failure)
    try:
        order = [t.name for t in Base.metadata.sorted_tables]
        print(f"[OK] FK dependency order resolves: {' -> '.join(order)}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"FK resolution failed: {exc!r}")
        order = []

    for table_name, expected_fks in EXPECTED_FKS.items():
        table = tables.get(table_name)
        if table is None:
            continue
        actual = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
        if actual != expected_fks:
            failures.append(
                f"{table_name}: FK mismatch expected={sorted(expected_fks)} "
                f"actual={sorted(actual)}"
            )
        else:
            print(f"[OK] {table_name}: {len(actual)} foreign keys correct")

    # 4. Relationships configure (raises on ambiguous/unresolvable mappers)
    try:
        configure_mappers()
        print("[OK] all relationships configured")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"relationship configuration failed: {exc!r}")

    # 5a. Indexes
    for table_name, expected in EXPECTED_INDEXES.items():
        table = tables.get(table_name)
        if table is None:
            continue
        actual = {idx.name for idx in table.indexes}
        absent = expected - actual
        if absent:
            failures.append(f"{table_name}: missing indexes {sorted(absent)}")
        else:
            print(f"[OK] {table_name}: indexes present ({len(expected)})")

    # 5b. Unique constraints
    for table_name, expected in EXPECTED_UNIQUE_CONSTRAINTS.items():
        table = tables.get(table_name)
        if table is None:
            continue
        actual = {c.name for c in table.constraints if c.__class__.__name__ == "UniqueConstraint"}
        absent = expected - actual
        if absent:
            failures.append(f"{table_name}: missing unique constraints {sorted(absent)}")
        else:
            print(f"[OK] {table_name}: unique constraints present")

    # 5c. CHECK constraints
    for table_name, expected in EXPECTED_CHECK_CONSTRAINTS.items():
        table = tables.get(table_name)
        if table is None:
            continue
        actual = {c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"}
        absent = expected - actual
        if absent:
            failures.append(f"{table_name}: missing check constraints {sorted(absent)}")
        else:
            print(f"[OK] {table_name}: check constraints present ({len(expected)})")

    if failures:
        print("\nVALIDATION FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nAll model validations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())