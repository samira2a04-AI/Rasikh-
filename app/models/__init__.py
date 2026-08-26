"""SQLAlchemy models for the Rasikh Legal Platform.

Importing this package registers every model class with ``Base.metadata``
(docs/data-schema.md §3). Alembic autogenerate can target
``app.database.base.Base.metadata`` once configured.
"""

from app.database.base import Base
from app.models.access_decision import AccessDecision
from app.models.analysis_run import AnalysisRun
from app.models.approval_decision import ApprovalDecision
from app.models.audit_event import AuditEvent
from app.models.citation import Citation
from app.models.contract import Contract
from app.models.contract_clause import ContractClause
from app.models.data_room_file import DataRoomFile
from app.models.draft import Draft
from app.models.escalation import Escalation
from app.models.finding import Finding
from app.models.matter_assignment import MatterAssignment
from app.models.obligation import Obligation
from app.models.organisation import Organisation
from app.models.request import Request
from app.models.review_standard_clause import ReviewStandardClause
from app.models.team_member import TeamMember
from app.models.user import User

__all__ = [
    "Base",
    "AccessDecision",
    "AnalysisRun",
    "ApprovalDecision",
    "AuditEvent",
    "Citation",
    "Contract",
    "ContractClause",
    "DataRoomFile",
    "Draft",
    "Escalation",
    "Finding",
    "MatterAssignment",
    "Obligation",
    "Organisation",
    "Request",
    "ReviewStandardClause",
    "TeamMember",
    "User",
]