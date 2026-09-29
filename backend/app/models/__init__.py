"""Import all models so SQLAlchemy metadata / Alembic see every table."""

from app.models.compliance import ComplianceItem, Regulation
from app.models.contractor import Contract, Contractor
from app.models.field import AttendanceRecord, CorrectiveAction, Inspection, MediaFile, Violation
from app.models.governance import (
    Anomaly,
    AuditLog,
    ChatMessage,
    ChatSession,
    Document,
    MLModel,
    Notification,
    OutboxEvent,
    ProcessedEvent,
    Report,
    RiskScore,
)
from app.models.operations import EnvironmentReading, Grievance, ProductionRecord
from app.models.org import Mine, PushSubscription, Subsidiary, User

__all__ = [
    "Anomaly",
    "AttendanceRecord",
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "ComplianceItem",
    "Contract",
    "Contractor",
    "CorrectiveAction",
    "Document",
    "EnvironmentReading",
    "Grievance",
    "Inspection",
    "MLModel",
    "MediaFile",
    "Mine",
    "Notification",
    "OutboxEvent",
    "ProcessedEvent",
    "ProductionRecord",
    "PushSubscription",
    "Regulation",
    "Report",
    "RiskScore",
    "Subsidiary",
    "User",
    "Violation",
]
