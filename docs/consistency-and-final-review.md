git# Rasikh — Cross-Document Consistency Check and Final Design Review

*Performed after `docs/PRD.md`, `docs/system-architecture.md`, and `docs/data-schema.md` were completed, per Part 5 and Part 6 of the design brief.*

---

## Part 5 — Cross-Document Consistency Check

### Requirements Coverage
Every FR, SEC, GRD, AI, ESC, APR, OBL, EVAL, and NFR requirement ID from the Requirements Inventory appears in the PRD (§6–§11) and is carried into the Architecture (§13 traceability table) and Data Schema (§13 traceability table). **Result: Pass.**

### Architecture Coverage
Every PRD capability in §5 (Core User Workflows) and §6 (Functional Requirements) maps to at least one Architecture component in §3, and every component in §3 is justified by at least one requirement (no component was added without a supporting requirement — e.g., no "notification service" or "analytics dashboard" component was introduced, consistent with FR-034's explicit "counts panel, not a full analytics dashboard"). **Result: Pass.**

### Data Coverage
Every persistent business concept named by the Architecture (matters, contracts, clauses, files, requests, findings, citations, obligations, escalations, drafts, approvals, audit events) has a corresponding entity in the Data Schema §2. No architecture component references a business concept without a modeled entity. **Result: Pass.**

### Security Consistency
- PRD §7 states the access-before-retrieval rule (SEC-002, Rule 1) and the records-not-claims rule (SEC-003, Rule 2).
- Architecture §5 implements both as structural/deterministic checks, not prompt instructions (SEC-005), and describes how Document Access has no callable path without a prior positive Access Control decision.
- Data Schema §4 and §12 model `AccessDecision` with a `basis` field that can only reference `MatterAssignment`, and describe the query-level enforcement that content joins require a prior authorized `AccessDecision`.

All three documents describe the same rule the same way: access is a code-level gate evaluated only from assignment records, before any document read. **Result: Pass.**

### Grounding Consistency
- PRD §8 requires every finding to carry a citation or an explicit "not in the documents" statement (FR-019, FR-020, GRD-001–GRD-005).
- Architecture §6 describes the programmatic citation-existence check that enforces this before a finding reaches the lawyer queue.
- Data Schema §7 and §12 encode this as a hard constraint: a grounded Finding has ≥1 Citation row referencing a real ContractClause/ReviewStandardClause; an ungrounded Finding has none.

All three documents converge on clause-level citation as a checkable property, not a stylistic goal. **Result: Pass.**

### Approval Consistency
- PRD §9 states nothing becomes final without a recorded lawyer approval (FR-032, Rule 5, APR-001–APR-005).
- Architecture §9 describes the Approval Gate as a structural check with no bypass path.
- Data Schema §9 and §12 model `Draft.approval_state` and `ApprovalDecision`, and explicitly note that no "final/delivered" state exists in the schema at all (consistent with OOS-007 — the product never delivers to a client itself).

**Result: Pass.**

### Escalation Consistency
- PRD §9 lists the four escalation triggers (litigation, statutory, Sharia-ruling, missed deadline) and states no drafted answer is produced for these (ESC-006).
- Architecture §6, §8, §9 route these cases to the Escalation component and explicitly withhold the Engine's drafting path for tagged hard cases.
- Data Schema §2.14 and §6 model `Escalation` with a `reason` enum matching exactly these four cases, linked from either `Request` or `Obligation`.

**Result: Pass.**

### Scope Consistency
Checked each Out-of-Scope item (OOS-001–OOS-007) against the Architecture and Data Schema for anything that would require it:
- **OOS-001 (real statutes):** No component or entity models statutory text or citations to Saudi law; `ReviewStandardClause` is the firm's own standard only.
- **OOS-002 (Sharia rulings):** `Finding.sharia_sensitive_flag` is a boolean flag, not a ruling field; Architecture explicitly stops Risk Analysis at flagging.
- **OOS-003 (litigation handling):** `Escalation.reason = 'litigation'` routes out of the system; no litigation-handling component exists.
- **OOS-004–OOS-006 (board portal, e-signature, entity filings):** No entities or components reference these; they do not appear anywhere in the three documents.
- **OOS-007 (live document sending):** No "delivery" or "send to client" entity/component exists anywhere in the design, as noted in Data Schema §9.

**Result: Pass — nothing out-of-scope was smuggled back in as a required feature.**

### Evaluation Consistency
Every item in PRD §11 (Success/Acceptance Criteria) states a test in parentheses, and each corresponds to a seeded scenario described in the Requirements Inventory §11.6 (27 typed requests) or §11.3 (seeded obligations). EVAL-001–EVAL-005 are reflected in PRD §11 item 16–17 and 20. **Result: Pass.**

---

## Part 6 — Final Design Review

1. **Can an unauthorized user retrieve a matter document?**
   No. Document Access has no callable path without a preceding positive `AccessDecision` (Architecture §5; Data Schema §4/§12). *(FR-004–FR-007, SEC-001–SEC-002)*

2. **Can a user claim authorization inside a prompt and bypass access control?**
   No. `AccessDecision.basis` only ever references `MatterAssignment`; the authorization function's input signature does not include `Request.raw_content` (Architecture §5; Data Schema §4). *(SEC-003, Rule 2)*

3. **Can the AI produce an answer without evidence?**
   No. A `Finding` can only be marked `grounded = true` if it has ≥1 real `Citation`; otherwise the Engine is required to emit the "not in the documents" result (Architecture §6; Data Schema §7/§12). *(FR-019–FR-020, GRD-001, GRD-005)*

4. **Can the AI invent a citation?**
   No, at two layers: `Citation` foreign keys can only reference clauses that actually exist (`ContractClause`/`ReviewStandardClause`), and the application-level check in Architecture §6 additionally confirms the cited clause was part of what Retrieval actually returned for that request. *(GRD-004, Rule 4)*

5. **Can the AI provide a Sharia ruling?**
   No. `Finding.sharia_sensitive_flag` is the only Sharia-related field; Architecture §7 explicitly stops processing at "flag for scholar review" and never proceeds to a ruling. *(OOS-002, ESC-003, FR-013)*

6. **Can the AI handle litigation itself?**
   No. Litigation-tagged requests are routed to `Escalation` with `reason = 'litigation'`; ESC-006 explicitly disallows a drafted answer for this case, and the Engine's drafting path is withheld once a request is tagged. *(FR-023, OOS-003)*

7. **Can an unapproved answer become final?**
   No. No "final/delivered" state exists in the schema; `Draft.approval_state` can only reach `approved` via a matching `ApprovalDecision` row tied to the current `Draft.version`. *(FR-032, Rule 5, APR-001–APR-005)*

8. **Can we identify which clause produced a finding?**
   Yes. Every grounded `Finding` links through `Citation` to a specific `ContractClause` or `ReviewStandardClause` row. *(FR-011, GRD-002–GRD-003)*

9. **Can we distinguish fixed expiry from auto-renewal?**
   Yes, by design intent: `Finding.tricky_case_type` explicitly enumerates `fixed_expiry` and `auto_renewal` as distinct values, and Architecture §7 requires the term/renewal checklist logic to look for renewal language specifically rather than stopping at the first term-length clause. *(FR-021)* Note: this is a design guarantee, not yet a tested guarantee — actual correctness depends on the Engine's implementation and must be confirmed against the seeded contracts in EVAL-001–EVAL-003.

10. **Can we detect an uncapped liability carve-out?**
    Yes, by the same design mechanism: `Finding.tricky_case_type` includes `capped_with_uncapped_carveout` as a distinct value from plain `capped_liability`, and Architecture §7 requires this to be reported as uncapped. *(FR-021)* Same testing caveat as above.

11. **Can Arabic contracts be cited correctly?**
    Yes, by design: `Contract.language` and `ContractClause.text` preserve the original language; Architecture §6–§7 require retrieval, analysis, and citation to operate on the Arabic source without a translation step, so a citation always points back to verifiable Arabic clause text. *(FR-022)*

12. **Can overdue obligations be detected?**
    Yes. `Obligation.band` is computed from `due_date` against threshold values sourced from `ReviewStandardClause` rows, and an `overdue` classification triggers an immediate `Escalation` row. *(FR-017–FR-018, OBL-005–OBL-006)*

13. **Can we trace a request from intake to final decision?**
    Yes. `AuditEvent` rows accumulate against `Request.request_id` at every lifecycle stage (Architecture §4 and §10; Data Schema §10), and `Request.status` reflects the same lifecycle. *(FR-033, NFR-002)*

14. **Can every critical requirement be mapped to an implementation component and test?**
    Yes — see the traceability tables in Architecture §13 and Data Schema §13, which map every requirement ID to a component, data entity, and a corresponding seeded test from the Requirements Inventory's test-data description (§11.6) or the obligations sweep (§11.3, EVAL-004).

**Overall result: no "no" answers.** The design as specified satisfies all fourteen review questions. The two items flagged with a testing caveat (9 and 10) are design guarantees that still require confirmation against actual Engine behavior once built — this is exactly what EVAL-001–EVAL-003 (outcome and process evaluation against the seeded contract set) are for, and is noted here rather than treated as resolved by design alone.

---

## Open Questions Summary

Carried forward from the three documents, for visibility in one place:

| # | Open Question | Where raised |
|---|---|---|
| 1 | Whether "Lawyer/Reviewer" and "Scholar" are distinct account types or capabilities held by Partner/Associate accounts | PRD §4, Data Schema §2.1 |
| 2 | Exact numeric obligation thresholds (days defining urgent/reminder bands) and exact risk-taxonomy labels — intentionally not hard-coded, read from the review standard at runtime | PRD §10, Architecture §7, Data Schema §2.11 |
| 3 | Exact scope of the privilege check (matter-level exception vs. organisation-level) for the one privileged data-room file | Architecture §5, Data Schema §4 |
| 4 | Whether partner firm-wide access is modeled as an explicit `MatterAssignment` row per matter or a role-level rule | Data Schema §2.3, §4 |
| 5 | Whether data-room files need clause/section-level citation granularity (only contracts are explicitly described at clause level in the source data) | Data Schema §5 |
| 6 | No numeric non-functional performance targets (latency, concurrency) are defined in the source material | PRD §3 |
| 7 | No push-notification component is required by the sources beyond the review queue/counts panel | Architecture §3 |

These do not block the design as specified — each open question is resolved with a stated default or left flexible in a way that does not affect whether the requirement is satisfiable — but they should be confirmed against the actual `firm_team.json` and review-standard content before implementation begins.
