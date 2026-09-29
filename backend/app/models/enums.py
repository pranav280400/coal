"""Domain enumerations (stored as constrained VARCHAR for migration flexibility)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    CORPORATE = "corporate"
    MINE_OFFICIAL = "mine_official"
    REGULATOR = "regulator"
    CONTRACTOR = "contractor"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"


class MineType(StrEnum):
    OPENCAST = "opencast"
    UNDERGROUND = "underground"
    MIXED = "mixed"


class ComplianceCategory(StrEnum):
    SAFETY = "safety"
    ENVIRONMENT = "environment"
    PRODUCTION = "production"
    LABOUR = "labour"


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    DUE = "due"
    IN_PROGRESS = "in_progress"
    OVERDUE = "overdue"
    VIOLATED = "violated"


class Frequency(StrEnum):
    ONE_TIME = "one_time"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    ANNUAL = "annual"


class InspectionType(StrEnum):
    ROUTINE = "routine"
    SAFETY = "safety"
    ENVIRONMENTAL = "environmental"
    COMPLIANCE_AUDIT = "compliance_audit"
    STATUTORY = "statutory"
    REINSPECTION = "reinspection"


class InspectionOutcome(StrEnum):
    COMPLIANT = "compliant"
    MINOR_ISSUES = "minor_issues"
    NON_COMPLIANT = "non_compliant"
    PENDING = "pending"


class InspectionStatus(StrEnum):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    REVIEWED = "reviewed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_WEIGHT = {Severity.LOW: 1, Severity.MEDIUM: 3, Severity.HIGH: 7, Severity.CRITICAL: 15}


class ViolationKind(StrEnum):
    VIOLATION = "violation"
    SAFETY_OBSERVATION = "safety_observation"
    INCIDENT = "incident"


class ViolationStatus(StrEnum):
    OPEN = "open"
    ACTION_ASSIGNED = "action_assigned"
    PENDING_VERIFICATION = "pending_verification"
    ESCALATED = "escalated"
    CLOSED = "closed"


class DetectedBy(StrEnum):
    AI = "ai"
    HUMAN = "human"
    SYSTEM = "system"  # automated limit checks (e.g. environmental readings above the statutory limit)


class ActionStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    OVERDUE = "overdue"


class ContractorStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLACKLISTED = "blacklisted"


class ContractStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class Shift(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    GENERAL = "general"


class DocumentType(StrEnum):
    STATUTORY_RETURN = "statutory_return"
    INSPECTION_REPORT = "inspection_report"
    PERMIT = "permit"
    LICENSE = "license"
    CIRCULAR = "circular"
    REGULATION = "regulation"
    EVIDENCE = "evidence"
    OTHER = "other"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportScope(StrEnum):
    MINE = "mine"
    SUBSIDIARY = "subsidiary"
    NATIONAL = "national"


class NotificationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AnomalyKind(StrEnum):
    RECURRING_VIOLATION = "recurring_violation"
    OPERATIONAL = "operational"
    ATTENDANCE_DROP = "attendance_drop"
    GEOFENCE = "geofence"


class AnomalyStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class GrievanceCategory(StrEnum):
    WAGES = "wages"
    SAFETY = "safety"
    WORKING_CONDITIONS = "working_conditions"
    HARASSMENT = "harassment"
    WELFARE = "welfare"
    CONTRACTOR_DISPUTE = "contractor_dispute"
    ENVIRONMENT = "environment"
    OTHER = "other"


class GrievanceStatus(StrEnum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"


class EnvParameter(StrEnum):
    PM10 = "pm10"
    PM2_5 = "pm2_5"
    SO2 = "so2"
    NO2 = "no2"
    NOISE_DAY = "noise_day"
    NOISE_NIGHT = "noise_night"
    WATER_PH = "water_ph"
    WATER_TSS = "water_tss"
    WATER_OIL_GREASE = "water_oil_grease"
    WATER_COD = "water_cod"
