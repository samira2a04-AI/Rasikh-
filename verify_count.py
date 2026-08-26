from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import ContractClause, ReviewStandardClause

engine = create_engine('postgresql+psycopg://postgres:11120042018.Sa@localhost:5432/rasikh')
s = Session(engine)

rs = s.query(ReviewStandardClause).filter(ReviewStandardClause.embedding != None).all()
cc = s.query(ContractClause).filter(ContractClause.embedding != None).all()

print(f"ReviewStandardClause generated: {len(rs)}/31")
print(f"ContractClause generated: {len(cc)}/74")
if rs:
    print(f"Dimension: {len(rs[0].embedding)}")
