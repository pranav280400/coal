// Types mirroring the FastAPI schemas (backend/app/schemas).

export type Role = "admin" | "corporate" | "mine_official" | "regulator" | "contractor";
export type Severity = "low" | "medium" | "high" | "critical";
export type Category = "safety" | "environment" | "production" | "labour";
export type ComplianceStatus = "compliant" | "due" | "in_progress" | "overdue" | "violated";
export type Frequency = "one_time" | "monthly" | "quarterly" | "half_yearly" | "annual";
export type InspectionType = "routine" | "safety" | "environmental" | "compliance_audit" | "statutory" | "reinspection";
export type InspectionOutcome = "compliant" | "minor_issues" | "non_compliant" | "pending";
export type ViolationStatus = "open" | "action_assigned" | "pending_verification" | "escalated" | "closed";
export type ViolationKind = "violation" | "safety_observation" | "incident";
export type ActionStatus = "assigned" | "in_progress" | "submitted" | "verified" | "rejected" | "overdue";
export type ProcessingStatus = "pending" | "processing" | "completed" | "failed";
export type DocumentType =
  | "statutory_return" | "inspection_report" | "permit" | "license" | "circular" | "regulation" | "evidence" | "other";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface MineBrief {
  id: string;
  code: string;
  name: string;
}
export interface PersonBrief {
  id: string;
  full_name: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  designation: string | null;
  phone: string | null;
  role: Role;
  status: "pending" | "active" | "disabled";
  subsidiary_id: string | null;
  mine_id: string | null;
  contractor_id: string | null;
  mine: MineBrief | null;
  preferred_language: string;
  notification_prefs: Record<string, boolean>;
  last_login_at: string | null;
  created_at: string;
  access_request_note?: string | null;
}
export interface Me extends User {
  permissions: string[];
  subsidiary_name: string | null;
}

export interface Subsidiary {
  id: string;
  code: string;
  name: string;
  headquarters: string | null;
}
export interface Mine {
  id: string;
  subsidiary_id: string;
  subsidiary: Subsidiary;
  code: string;
  name: string;
  mine_type: "opencast" | "underground" | "mixed";
  state: string;
  district: string | null;
  latitude: number;
  longitude: number;
  boundary_geojson: { type: string; coordinates: number[][][] } | null;
  capacity_mtpa: number | null;
  workforce: number | null;
  is_active: boolean;
  risk_score: number | null;
  risk_updated_at: string | null;
}
export interface MinePoint {
  id: string;
  code: string;
  name: string;
  subsidiary_code: string;
  latitude: number;
  longitude: number;
  status: "compliant" | "minor_issues" | "non_compliant";
  open_violations: number;
  critical_violations: number;
  overdue_compliance: number;
  compliance_rate: number;
  risk_score: number | null;
}

export interface Regulation {
  id: string;
  code: string;
  act: string;
  section: string | null;
  title: string;
  category: Category;
  text: string;
  authority: string | null;
  is_embedded: boolean;
}

export interface ComplianceItem {
  id: string;
  mine_id: string;
  mine: MineBrief;
  category: Category;
  title: string;
  description: string | null;
  regulation_id: string | null;
  regulation_ref: string | null;
  frequency: Frequency;
  due_date: string;
  status: ComplianceStatus;
  owner: PersonBrief | null;
  last_completed_at: string | null;
  evidence_document_id: string | null;
  completion_notes: string | null;
  escalated: boolean;
  created_at: string;
  updated_at: string;
}
export interface ComplianceSummary {
  overview: { compliant: number; in_progress: number; non_compliant: number };
  total: number;
  compliant: number;
  in_progress: number;
  due: number;
  overdue: number;
  violated: number;
  compliance_rate: number;
  strict_compliance_rate: number;
  by_category: Record<string, Record<string, number>>;
}

export interface ChecklistItem {
  item: string;
  passed: boolean;
  note?: string | null;
}
export interface Media {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  latitude: number | null;
  longitude: number | null;
  captured_at: string | null;
  created_at: string;
}
export interface Inspection {
  id: string;
  number: number;
  mine_id: string;
  mine: MineBrief;
  inspector: PersonBrief;
  inspection_type: InspectionType;
  title: string;
  notes: string;
  checklist: ChecklistItem[];
  latitude: number | null;
  longitude: number | null;
  geo_accuracy_m: number | null;
  distance_from_mine_km: number | null;
  geo_verified: boolean;
  inspected_at: string;
  status: "submitted" | "processing" | "reviewed";
  outcome: InspectionOutcome;
  ai_summary: string | null;
  ai_findings: {
    key_findings?: string[];
    hazards?: { description: string; severity: Severity; category: Category }[];
    recommended_actions?: string[];
  } | null;
  risk_score: number | null;
  source: string;
  created_at: string;
}
export interface InspectionDetail extends Inspection {
  media: Media[];
  violations: Violation[];
}

export interface Violation {
  id: string;
  number: number;
  mine_id: string;
  mine: MineBrief;
  inspection_id: string | null;
  contractor_id: string | null;
  kind: ViolationKind;
  category: Category;
  title: string;
  description: string;
  severity: Severity;
  severity_confirmed: boolean;
  ai_suggested_severity: Severity | null;
  ai_confidence: number | null;
  ai_rationale: string | null;
  ai_source: string | null;
  detected_by: "ai" | "human";
  status: ViolationStatus;
  risk_score: number | null;
  regulation_ref: string | null;
  latitude: number | null;
  longitude: number | null;
  occurred_at: string;
  escalation_level: number;
  closed_at: string | null;
  created_at: string;
}
export interface SimilarItem {
  source_type: string;
  source_id: string;
  title: string;
  snippet: string;
  score: number;
  mine_id: string | null;
}

export interface CorrectiveAction {
  id: string;
  violation_id: string;
  violation_number: number | null;
  violation_title: string | null;
  mine_name: string | null;
  title: string;
  description: string;
  assignee: PersonBrief;
  deadline: string;
  status: ActionStatus;
  completion_notes: string | null;
  submitted_at: string | null;
  verified_at: string | null;
  verification_notes: string | null;
  reinspection_id: string | null;
  created_at: string;
}

export interface Contract {
  id: string;
  contractor_id: string;
  mine: MineBrief;
  work_order_no: string;
  title: string;
  value_inr: string;
  start_date: string;
  end_date: string;
  workforce_count: number;
  status: "active" | "completed" | "terminated";
}
export interface Contractor {
  id: string;
  subsidiary_id: string;
  name: string;
  registration_no: string;
  gstin: string | null;
  category: string;
  contact_person: string;
  contact_email: string | null;
  contact_phone: string | null;
  address: string | null;
  status: "pending_verification" | "active" | "suspended" | "blacklisted";
  verified: boolean;
  compliance_score: number;
  risk_score: number | null;
  active_contracts: number;
  created_at: string;
}
export interface ContractorDetail extends Contractor {
  pan_masked: string | null;
  contracts: Contract[];
  open_violations: number;
  total_violations: number;
}

export interface Attendance {
  id: string;
  mine_id: string;
  worker_name: string;
  contractor_id: string | null;
  shift: "A" | "B" | "C" | "general";
  check_in_at: string;
  check_out_at: string | null;
  latitude: number | null;
  longitude: number | null;
  geo_verified: boolean;
  source: string;
}

export interface DocumentItem {
  id: string;
  mine_id: string | null;
  subsidiary_id: string | null;
  title: string;
  doc_type: DocumentType;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  ocr_status: ProcessingStatus;
  ocr_confidence: number | null;
  page_count: number | null;
  extracted_fields: Record<string, unknown> | null;
  summary: string | null;
  embedded_chunks: number;
  error: string | null;
  created_at: string;
}
export interface DocumentDetail extends DocumentItem {
  ocr_text: string | null;
}

export interface Report {
  id: string;
  title: string;
  scope: "mine" | "subsidiary" | "national";
  scope_id: string | null;
  period_start: string;
  period_end: string;
  status: ProcessingStatus;
  summary: string | null;
  metrics: { totals?: Record<string, number> } | null;
  scheduled: boolean;
  error: string | null;
  generated_at: string | null;
  created_at: string;
  has_pdf: boolean;
  has_xlsx: boolean;
}

export interface RiskEntry {
  entity_type: "mine" | "contractor";
  entity_id: string;
  name: string;
  code: string | null;
  score: number;
  band: "low" | "moderate" | "high" | "critical";
  factors: {
    features: Record<string, number>;
    drivers: { feature: string; label: string; value: number; contribution: number }[];
  };
  computed_at: string | null;
}
export interface Anomaly {
  id: string;
  mine_id: string | null;
  kind: "recurring_violation" | "operational" | "attendance_drop" | "geofence";
  title: string;
  description: string;
  metric: Record<string, unknown>;
  score: number;
  status: "open" | "acknowledged" | "resolved";
  detected_at: string;
}

export interface Notification {
  id: string;
  title: string;
  body: string;
  severity: "info" | "warning" | "critical";
  category: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  event_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: string | null;
  actor_name: string | null;
  mine_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ts: string;
  prev_hash: string;
  hash: string;
}

export interface Citation {
  index: number;
  source_type: string;
  source_id: string;
  title: string;
  score: number;
  snippet: string;
}
export interface ChatSession {
  id: string;
  title: string;
  language: string;
  created_at: string;
  updated_at: string;
}
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface DashboardSummary {
  generated_at: string;
  cached: boolean;
  kpis: {
    total_mines: number;
    new_mines_this_month: number;
    compliance_items: number;
    compliance_rate: number;
    open_violations: number;
    critical_violations: number;
    active_contractors: number;
    verified_contractors: number;
    inspections: number;
    inspections_this_month: number;
    inspections_change_pct: number | null;
    open_anomalies: number;
  };
  compliance: ComplianceSummary;
  recent_inspections: {
    id: string;
    number: number;
    mine_name: string;
    title: string;
    inspection_type: InspectionType;
    inspected_at: string;
    outcome: InspectionOutcome;
    geo_verified: boolean;
  }[];
  upcoming_deadlines: {
    id: string;
    title: string;
    mine_name: string;
    due_date: string;
    days_left: number;
    status: ComplianceStatus;
    category: Category;
  }[];
  violation_trends: { month: string; label: string; total: number; critical: number; major: number; minor: number; resolved: number }[];
  mine_locations: MinePoint[];
  high_risk_mines: { id: string; name: string; code: string; risk_score: number | null }[];
}

export interface SearchResults {
  mines: SearchHit[];
  inspections: SearchHit[];
  violations: SearchHit[];
  contractors: SearchHit[];
  regulations: SearchHit[];
}
export interface SearchHit {
  id: string;
  title: string;
  subtitle: string;
  href: string;
}

// ---------------------------------------------------------------- grievances
export type GrievanceStatus = "open" | "assigned" | "in_progress" | "resolved" | "closed" | "rejected";
export type GrievanceCategory =
  | "wages"
  | "safety"
  | "working_conditions"
  | "harassment"
  | "welfare"
  | "contractor_dispute"
  | "environment"
  | "other";

export interface Grievance {
  id: string;
  number: number;
  mine_id: string;
  mine: { id: string; code: string; name: string };
  category: GrievanceCategory;
  subject: string;
  description: string;
  priority: "low" | "medium" | "high" | "critical";
  status: GrievanceStatus;
  is_anonymous: boolean;
  raiser: { id: string; full_name: string } | null;
  assignee: { id: string; full_name: string } | null;
  contractor_id: string | null;
  due_at: string;
  escalation_level: number;
  resolution_notes: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  satisfaction: number | null;
  reopen_count: number;
  created_at: string;
  updated_at: string;
  is_mine: boolean;
  can_manage: boolean;
}

export interface GrievanceSummary {
  total: number;
  open: number;
  overdue: number;
  resolved: number;
  closed: number;
  avg_resolution_hours: number | null;
  avg_satisfaction: number | null;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
}

// ---------------------------------------------------- production & environment
export interface ProductionRecord {
  id: string;
  mine_id: string;
  mine: { id: string; code: string; name: string };
  period: string;
  target_t: number | null;
  produced_t: number;
  dispatched_t: number;
  overburden_bcm: number | null;
  closing_stock_t: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductionSummary {
  months: { period: string; target_t: number; produced_t: number; dispatched_t: number; overburden_bcm: number }[];
  ytd_produced_t: number;
  ytd_dispatched_t: number;
  ytd_target_t: number;
  achievement_pct: number | null;
  last_month_change_pct: number | null;
  shortfall_mines: { mine_id: string; code: string; name: string; produced_t: number; target_t: number; achievement_pct: number }[];
}

export type EnvParameter =
  | "pm10"
  | "pm2_5"
  | "so2"
  | "no2"
  | "noise_day"
  | "noise_night"
  | "water_ph"
  | "water_tss"
  | "water_oil_grease"
  | "water_cod";

export interface EnvLimit {
  parameter: EnvParameter;
  label: string;
  unit: string;
  group: "air" | "noise" | "water";
  limit_min: number | null;
  limit_max: number | null;
  standard: string;
}

export interface EnvReading {
  id: string;
  mine_id: string;
  mine: { id: string; code: string; name: string };
  parameter: EnvParameter;
  value: number;
  unit: string;
  limit_min: number | null;
  limit_max: number | null;
  exceeded: boolean;
  station: string;
  sampled_at: string;
  source: "manual" | "lab" | "sensor";
  latitude: number | null;
  longitude: number | null;
  notes: string | null;
  violation_id: string | null;
  created_at: string;
}

export interface EnvParamStatus {
  parameter: EnvParameter;
  label: string;
  unit: string;
  group: "air" | "noise" | "water";
  limit_min: number | null;
  limit_max: number | null;
  latest: number | null;
  latest_at: string | null;
  average_30d: number | null;
  readings_30d: number;
  exceedances_30d: number;
}

export interface EnvSummary {
  parameters: EnvParamStatus[];
  exceedances_30d: number;
  readings_30d: number;
  compliance_pct: number | null;
  worst_mines: { mine_id: string; code: string; name: string; exceedances: number }[];
}
