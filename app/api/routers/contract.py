from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.models import Contract, ContractClause, Organisation
from app.api.schemas.contract import ContractSummary
from app.api.auth_dependencies import CurrentUser, get_current_user
from app.services import access_control

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/organisations/{org_id}/contracts", response_model=list[ContractSummary])
def list_contracts(
    org_id: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    if current_user.member_id:
        access_res = access_control.check_access(db, member_id=current_user.member_id, org_id=org_id)
        if not access_res.authorized:
            raise HTTPException(status_code=403, detail="Not authorized to access contracts for this matter")
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
