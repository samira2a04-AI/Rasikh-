import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import SessionLocal
from app.services import request_intake

client = TestClient(app, raise_server_exceptions=False)

response = client.post('/auth/login', json={'email': 'lawyer@rasikh.local', 'password': 'Demo1234!'})
headers = {'Authorization': f'Bearer {response.json()["access_token"]}'}

req_id = f'REQ-TEST-{uuid.uuid4().hex[:8]}'
with SessionLocal() as session:
    req = request_intake.submit_request(
        session, request_id=req_id, requester_id='L-01', raw_content='Review this'
    )
    req.status = 'insufficient'
    session.commit()

response = client.patch(f'/requests/{req_id}/resolve', json={'org_id': 'ORG-1001', 'request_type': 'contract_review'}, headers=headers)
print('Response 1001:', response.status_code, response.text)

response2 = client.patch(f'/requests/{req_id}/resolve', json={'org_id': 'ORG-1009', 'request_type': 'contract_review'}, headers=headers)
print('Response 1009:', response2.status_code, response2.text)

response3 = client.patch(f'/requests/{req_id}/resolve', json={'org_id': 'ORG-1003', 'request_type': 'contract_review'}, headers=headers)
print('Response 1003:', response3.status_code, response3.text)
