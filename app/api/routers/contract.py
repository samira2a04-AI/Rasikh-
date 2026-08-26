from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.models import Contract, ContractClause, Organisation
from app.api.schemas.contract import ContractSummary

router = APIRouter()

@router.get("/organisations/{org_id}/contracts", response_model=list[ContractSummary])
def list_contracts(org_id: str, db: Session = Depends(get_db)):
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    contracts = db.query(Contract).filter(Contract.org_id == org_id).all()
    result = []
    for c in contracts:
        clause_count = db.query(ContractClause).filter(ContractClause.contract_id == c.contract_id).count()
        result.append(ContractSummary(
            contract_id=c.contract_id,
            title=c.title,
            clause_count=clause_count,
            has_clauses=clause_count > 0,
        ))
    return result
