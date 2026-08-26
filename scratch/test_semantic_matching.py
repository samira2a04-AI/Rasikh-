import sys
from pathlib import Path

REPO_ROOT = Path("c:/Users/user/OneDrive/Desktop/Exology/Rasikh_Legal_Platform")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database.connection import SessionLocal
from app.models import Contract, ContractClause, ReviewStandardClause

_STANDARD_TOPIC_KEYWORDS = {
    "1.1": {"term", "renewal", "duration", "expiry", "expire", "commence", "effective", "auto-renew", "period"},
    "1.2": {"liability", "indemnify", "indemnity", "indemnification", "limitation", "cap", "loss", "damage", "carve-out"},
    "1.3": {"payment", "pay", "fee", "price", "invoice", "currency", "amount", "due", "schedule", "billing", "usd", "sar", "price"},
    "1.4": {"terminate", "termination", "cancel", "cancellation", "breach", "notice", "convenience"},
    "1.5": {"governing", "law", "jurisdiction", "dispute", "court", "governed", "arbitration", "saudi", "english", "rules"},
    "1.6": {"confidential", "confidentiality", "disclosure", "nondisclosure", "privacy", "secret", "proprietary", "data"},
    "4.1": {"interest", "per annum", "usury", "riba", "finance charge"},
    "4.2": {"uncertainty", "speculation", "undefined", "gharar"},
    "4.3": {"penalty", "liquidated", "damages", "late fee", "fine", "sanction", "late payment"},
}

_STOPWORDS = frozenset(
    """the a an of and or to in for with on by is are be been was were not
    shall should must may might will would can could this that these those
    any all each such from at as it its into upon under over between during
    before after within without per their his her our your they them he she
    we you i if then else when where which who whom whose what how no yes""".split()
)

def _content_words(text: str) -> set[str]:
    return {w.strip(".,;:()[]\"'").lower() for w in text.split() if len(w) > 2 and w.lower() not in _STOPWORDS}

def test_matching():
    with SessionLocal() as session:
        contracts = session.query(Contract).all()
        for c in contracts:
            clauses = session.query(ContractClause).filter(ContractClause.contract_id == c.contract_id).all()
            print(f"\n=================== CONTRACT {c.contract_id}: {c.title[:50]} ===================")
            for num, topic_words in _STANDARD_TOPIC_KEYWORDS.items():
                best_clause = None
                best_overlap = 0
                for cc in clauses:
                    c_words = _content_words(cc.text)
                    overlap = len(topic_words & c_words)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_clause = cc
                if best_clause:
                    print(f"  Std {num:<4} -> Clause {best_clause.clause_label:<4} (matched {best_overlap} keywords): {best_clause.text[:70]}...")
                else:
                    print(f"  Std {num:<4} -> NOT ADDRESSED IN CONTRACT")

if __name__ == "__main__":
    test_matching()
