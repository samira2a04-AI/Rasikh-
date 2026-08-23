# Rasikh — Legal & Governance Assistant · Data

Everything the product works from. Plain files, no database. Today's date is 2026-07-01.

## `rulebook/`  — the firm's review standard (RAG corpus)
How this firm reads its obligations and instructs its people — not the law itself. About
thirty-five numbered clauses across six files: the review standard and the two gates
(cite-or-say-you-can't, lawyer approval, access-by-matter, privilege), the contract-review
checklist, the risk taxonomy, the Sharia-sensitive constructs to detect and flag, governance
and obligations with alert thresholds, and consultations, triage & escalation. Deliberately too
long to paste in one go, with tricky pairs (a fixed-term expiry vs an auto-renewal; capped vs
uncapped liability; a construct to flag for scholar review vs one to answer) so the product must
retrieve the right clause, not guess.

## The lookups — access is by matter
`firm_team.json` — 10 members with role and **matter access** (partners firm-wide; associates
and paralegals scoped to named orgs); `can_approve` marks who may record approval.
`organizations.json` — 150 client orgs with sector, type, status, and assigned team.
`obligations.json` — governance and contract deadlines with due dates, owners, and (against
today) one **overdue**, one **urgent**, one **reminder**, the rest on track.

## `contracts/`  — 12 contracts (3 in Arabic)
Short agreements, each headed with its matter org. They carry the checklist's tricky pairs:
**C-01 fixed-term expiry vs C-02 auto-renewal**; **C-03 uncapped-via-carve-out vs C-04 cleanly
capped**; **C-05 late-payment interest + penalty** (Sharia flags); **C-06 missing governing
law + signature block**; and the Arabic set **C-09 (auto-renew + penalty), C-10 (uncapped +
interest), C-11 (missing governing law)**.

## `dataroom/`  — 6 access-controlled files
One per matter, including **DR-04, a privileged attorney-work-product memo** that must never
reach anyone outside the Manar matter team or any counterparty.

## `requests/`  — the work items (27)
Typed requests from firm members (and one from outside), 2 in Arabic. They seed the test set and
span every decision: REVIEW_CONTRACT (the pairs above), ANSWER_CONSULTATION (grounded, cited),
PREP_MEETING, FLAG_OBLIGATION, ESCALATE (litigation, a statutory question, a request to rule on
Sharia, a missed deadline), REQUEST_INFO (too thin to act), NOT_IN_DOCUMENTS (the honest 'not in
here'), REFUSE_ACCESS (a privileged-file grab from outside the matter, and a colleague off the
matter), and REFUSE_OVERRIDE (invent-a-citation-and-skip-approval, and assert-blanket-compliance).

## `answer_key.json`  — ground truth (instructor copy)
Per request: the matter, the access decision, the decision, the governing clause(s), the exact
citations a correct answer must carry, the tools a correct product would use, and the rationale.
An **ALERTS** entry records what a correct obligations sweep must flag against 2026-07-01.
