/**
 * Admin portal types: mirrors of the FastAPI `/api/admin/*` JSON (backend/app/api/schemas_admin.py,
 * routes_admin.py and app/bss/{types,network,ops,monitor,offers}.py). Field names match the backend
 * exactly. Money is a JSON number; dates and datetimes are ISO strings. MSISDNs are always masked.
 */
import type { DateString, DateTimeString, UUID } from './common';
import type {
  AccountSummary,
  CasePriority,
  CaseSource,
  CaseStatus,
  IncidentKind,
  IncidentStatus,
  IncidentView,
  PackageView,
  PlanType,
  TransactionView,
  TxnStatus,
  TxnType,
} from './portal';

export type SubscriberStatus = 'active' | 'suspended';
export type NotificationKind = 'pack_expiring' | 'low_balance' | 'low_data' | 'case_update';
export type OfferAudience = 'all' | 'prepaid' | 'postpaid' | 'specific';
export type OfferKind = 'points' | 'cashback' | 'pack';
export type DistrictHealthState = 'normal' | 'degraded' | 'maintenance';
export type AiMonitorWindow = '24h' | '7d';

/** Pagination envelope shared by the admin lists. */
export interface AdminPage<T> {
  items: T[];
  total: number;
}

// --- control center -----------------------------------------------------------------------

export interface ActivityPoint {
  date: DateString;
  recharge_amount: number;
  cases_created: number;
}

export interface AttentionItem {
  kind: string;
  title: string;
  detail: string;
  severity: string;
  /** An in-app route, e.g. `/dashboard/cases`. */
  href: string;
}

/** `GET /api/admin/overview`. */
export interface Overview {
  subscribers: { total: number; prepaid: number; postpaid: number };
  recharge_today: { amount: number; count: number };
  cases: { open: number; high_open: number };
  ai: { chats_24h: number; resolution_rate: number };
  activity: ActivityPoint[];
  health: {
    recharge_success_rate_24h: number | null;
    median_first_response_s: number | null;
    active_incidents: number;
    pending_transactions: number;
  };
  attention: AttentionItem[];
}

// --- subscribers --------------------------------------------------------------------------

export interface SubscriberItem {
  id: UUID;
  full_name: string;
  msisdn_masked: string;
  plan_type: PlanType;
  district: string;
  status: SubscriberStatus;
  main_balance: number;
  postpaid_due: number;
  joined_on: DateString;
}

export interface SubscriberDetailHead extends SubscriberItem {
  reward_points: number;
  preferred_language: string;
}

export interface SubscriberListParams {
  q?: string;
  plan_type?: PlanType;
  status?: SubscriberStatus;
  /** 1..100, default 25 */
  limit?: number;
  offset?: number;
}

export type SubscriberList = AdminPage<SubscriberItem>;

export interface NotificationView {
  id: UUID;
  kind: NotificationKind;
  title: string;
  body: string;
  /** pack_expiring {package_name, expires_at}; low_balance {balance}; low_data {package_name,
   * data_left_mb}; case_update {case_ref, status}. */
  payload: Record<string, unknown>;
  created_at: DateTimeString;
  read_at: DateTimeString | null;
}

export interface CaseView {
  ref: string;
  category: string;
  description: string;
  priority: CasePriority;
  status: CaseStatus;
  source: CaseSource;
  created_at: DateTimeString;
  updated_at: DateTimeString;
  resolved_at: DateTimeString | null;
}

/** `GET /api/admin/subscribers/{id}`. */
export interface SubscriberDetail {
  subscriber: SubscriberDetailHead;
  summary: AccountSummary;
  transactions: TransactionView[];
  cases: CaseView[];
  notifications: NotificationView[];
}

// --- transactions -------------------------------------------------------------------------

export interface AdminTransaction extends TransactionView {
  subscriber_name: string;
  msisdn_masked: string;
}

export interface TransactionListParams {
  status?: TxnStatus;
  type?: TxnType;
  /** Matches reference, subscriber name or masked number. */
  q?: string;
  /** 1..90, default 7 */
  days?: number;
  /** 1..100, default 25 */
  limit?: number;
  offset?: number;
}

export type TransactionList = AdminPage<AdminTransaction>;

/** `GET /api/admin/transactions/stats`. */
export interface TransactionStats {
  volume: number;
  attempts: number;
  success: number;
  pending: number;
  failed: number;
  success_rate: number | null;
}

// --- support queue ------------------------------------------------------------------------

export interface AdminCase extends CaseView {
  subscriber_name: string;
  msisdn_masked: string;
}

export interface CaseListParams {
  status?: CaseStatus;
  priority?: CasePriority;
  /** Everything not resolved (open and in review), as the Open cases tile counts. */
  open_only?: boolean;
  /** 1..100, default 25 */
  limit?: number;
  offset?: number;
}

export type CaseList = AdminPage<AdminCase>;

/** `GET /api/admin/cases/stats`. */
export interface CaseStats {
  open: number;
  high_open: number;
  avg_resolution_hours_7d: number | null;
  ai_assisted_share_7d: number;
}

// --- network ------------------------------------------------------------------------------

export interface IncidentAdminView extends IncidentView {
  id: UUID;
  active: boolean;
}

export interface DistrictHealth {
  district: string;
  health: DistrictHealthState;
  incidents: number;
}

/** `GET /api/admin/network`. */
export interface NetworkOverview {
  districts: DistrictHealth[];
  incidents: IncidentAdminView[];
}

export interface IncidentCreate {
  district: string;
  area: string;
  kind: IncidentKind;
  status: IncidentStatus;
  message: string;
  starts_at?: DateTimeString | null;
  ends_at?: DateTimeString | null;
}

// --- AI monitor ---------------------------------------------------------------------------

export interface Intent {
  label: string;
  count: number;
  share: number;
}

export interface MonitorMetrics {
  chats: number;
  turns: number;
  fallback_rate: number;
  resolution_rate: number;
  median_first_response_s: number | null;
  p95_first_response_s: number | null;
  intents: Intent[];
}

export interface ReviewItem {
  conversation_id: UUID;
  started_at: DateTimeString;
  subscriber_name: string | null;
  no_tool_turns: number;
  preview: string;
}

export interface AuditItem {
  created_at: DateTimeString;
  actor: string;
  action: string;
  subscriber_name: string | null;
  msisdn_masked: string | null;
  detail: string;
}

/** `GET /api/admin/ai-monitor`. */
export interface AiMonitor {
  metrics: MonitorMetrics;
  review_queue: ReviewItem[];
  audit_trail: AuditItem[];
}

// --- nudges -------------------------------------------------------------------------------

/** `POST /api/admin/nudges/run`: notifications created, per kind. */
export interface NudgeRunResult {
  created: Partial<Record<NotificationKind, number>>;
}

// --- offers -------------------------------------------------------------------------------

export interface OfferSubscriberRef {
  id: UUID;
  full_name: string;
  msisdn_masked: string;
}

export interface AdminOffer {
  id: UUID;
  title: string;
  description: string | null;
  terms: string | null;
  kind: OfferKind;
  package_id: UUID | null;
  package_name: string | null;
  points_cost: number | null;
  cashback_percent: number | null;
  cashback_cap: number | null;
  min_recharge: number | null;
  audience: OfferAudience;
  subscriber_ids: UUID[];
  subscribers: OfferSubscriberRef[];
  starts_on: DateString | null;
  ends_on: DateString | null;
  is_active: boolean;
  /** Redemptions so far. */
  redemptions: number;
}

export interface OfferCreate {
  title: string;
  description?: string | null;
  terms?: string | null;
  package_id?: UUID | null;
  points_cost?: number | null;
  cashback_percent?: number | null;
  cashback_cap?: number | null;
  min_recharge?: number | null;
  audience?: OfferAudience;
  subscriber_ids?: UUID[];
  starts_on?: DateString | null;
  ends_on?: DateString | null;
  is_active?: boolean;
}

/** Only the fields sent change; the backend re-validates the whole offer. */
export type OfferPatch = Partial<OfferCreate>;

/** `GET /api/admin/packages`: the active catalogue (for the offer form's pack picker). */
export interface AdminPackage extends PackageView {
  id: UUID;
}
