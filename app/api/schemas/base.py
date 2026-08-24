"""Shared Pydantic configuration for API response/request schemas.

``from_attributes=True`` lets a response model be populated directly from a
SQLAlchemy ORM instance via ``model_validate``. We never serialize raw ORM
objects through FastAPI's generic encoder: every response is built from an
explicit dict first, so the JSON contract is controlled and stable rather than
being derived from whatever relationships happen to be loaded.
"""
