import os
import json
from sqlalchemy import select
from app.database.connection import SessionLocal
from app.models import Request, ContractClause, ReviewStandardClause, Contract
from app.services.llm import evaluate_clauses_via_llm

def test_eval():
    with SessionLocal() as session:
        # Get request
        request_id = "b149cf87-a055-4c06-972d-5e1a15ddeda3"
        org_id = "ORG-1007"
        
        # Get a contract for the org
        contracts = session.scalars(select(Contract).where(Contract.org_id == org_id)).all()
        contract_id = contracts[0].contract_id if contracts else None
        print(f"Contract ID: {contract_id}")

        contract_clauses = session.scalars(
            select(ContractClause).where(ContractClause.contract_id == contract_id)
        ).all()
        print(f"Found {len(contract_clauses)} contract clauses")
        
        standard_clauses = session.scalars(
            select(ReviewStandardClause)
        ).all()
        print(f"Found {len(standard_clauses)} standard clauses")
        
        if not contract_clauses:
            print("No contract clauses found!")
            return
            
        contract_text = "\n".join(
            f"[Clause ID: {c.clause_id}] (Label: {c.clause_label}) {c.text}"
            for c in contract_clauses
        )
        
        standard_text = "\n".join(
            f"[Standard Clause ID: {c.standard_clause_id}] (Number: {c.clause_number}) {c.text}"
            for c in standard_clauses
        )
        
        print("--- Contract Text ---")
        print(contract_text[:500] + "...")
        print("--- Standard Text ---")
        print(standard_text[:500] + "...")
        
        print("\nCalling LLM...")
        findings = evaluate_clauses_via_llm(contract_text, standard_text)
        print(f"\nLLM returned {len(findings)} findings")
        
        for f in findings:
            print("\nFinding:")
            print(f.model_dump_json(indent=2))

if __name__ == "__main__":
    test_eval()
