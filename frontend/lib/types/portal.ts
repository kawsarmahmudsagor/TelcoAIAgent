/**
 * Customer self-care portal types: mirrors of the FastAPI `/api/demo/*` and `/api/me/*` JSON
 * (backend/app/api/schemas_me.py, routes_demo.py and app/bss/types.py). Field names match the
 * backend exactly. Money is a JSON number; dates and datetimes are ISO strings.
 */
import type { DateString, DateTimeString, UUID } from './common';

export type PlanType = 'prepaid' | 'postpaid';
export type PackageKind = 'data' | 'voice' | 'bundle' | 'sms';
export type UsageKind = 'data' | 'voice' | 'sms' | 'vas';
export type TxnType = 'recharge' | 'purchase' | 'redeem';
export type TxnChannel = 'bkash' | 'nagad' | 'card' | 'balance' | 'points';
export type TxnStatus = 'success' | 'pending' | 'failed';
export type CasePriority = 'normal' | 'high';
export type CaseStatus = 'open' | 'in_review' | 'resolved';
export type CaseSource = 'agent' | 'portal' | 'admin';
export type IncidentKind = 'outage' | 'congestion' | 'maintenance';
export type IncidentStatus = 'investigating' | 'scheduled' | 'resolved';
export type PortalActionKind = 'purchase' | 'recharge' | 'redeem';

/** `GET /api/demo/personas` item. */
export interface PersonaCard {
  msisdn: string;
  masked_msisdn: string;
  full_name: string;
  plan_type: PlanType;
  district: string;
  headline: string;
}

/** `POST /api/auth/customer/signup`. */
export interface SignupRequest {
  full_name: string;
  /** Local 11-digit number, `01…`. */
  msisdn: string;
  district: string;
  plan_type: PlanType;
  /** 8 to 72 characters. */
  password: string;
}

/** `POST /api/auth/customer/reset/start`: the reset id and the simulated SMS. */
export interface ResetStart {
  reset_id: UUID;
  otp: OtpSms;
}

/** The signed-in customer (`GET /api/me`, `POST /api/demo/login`, the customer auth routes). */
export interface PortalMe {
  subscriber_id: UUID;
  full_name: string;
  first_name: string;
  msisdn: string;
  masked_msisdn: string;
  plan_type: PlanType;
  district: string;
}

export interface Allowance {
  data_left_mb: number;
  minutes_left: number;
  sms_left: number;
}

export interface SubscriptionView {
  package_code: string;
  package_name: string;
  data_left_mb: number;
  minutes_left: number;
  sms_left: number;
  expires_at: DateTimeString;
  auto_renew: boolean;
}

/** `GET /api/me/summary`. */
export interface AccountSummary {
  subscriber_id: UUID;
  full_name: string;
  masked_msisdn: string;
  plan_type: PlanType;
  district: string;
  main_balance: number;
  postpaid_due: number;
  reward_points: number;
  totals: Allowance;
  subscriptions: SubscriptionView[];
  nearest_expiry: DateTimeString | null;
  open_cases: number;
  district_incidents: number;
}

export interface UsageTotals {
  kind: UsageKind;
  amount: number;
  unit: string;
  charge: number;
}

/** `GET /api/me/usage`. */
export interface UsageBreakdown {
  period_days: number;
  totals: UsageTotals[];
  /** Data MB per local day (`[date, mb]`), oldest first. */
  daily: [DateString, number][];
}

/** `GET /api/me/transactions` item. */
export interface TransactionView {
  ref: string;
  type: TxnType;
  channel: TxnChannel;
  amount: number;
  target_msisdn: string | null;
  status: TxnStatus;
  failure_reason: string | null;
  created_at: DateTimeString;
  package_name: string | null;
  /** The offer's points cost on a redeem row, else null. */
  points_spent: number | null;
  /** Reward points a recharge row earned, else null. */
  points_earned: number | null;
}

export interface TransactionParams {
  type?: TxnType;
  status?: TxnStatus;
  days?: number;
  limit?: number;
}

/** `GET /api/me/packages` item. */
export interface PackageView {
  code: string;
  name: string;
  kind: PackageKind;
  data_mb: number;
  minutes: number;
  sms: number;
  validity_days: number;
  price: number;
  tag: string | null;
}

/** `GET /api/me/recommendations` item. */
export interface Recommendation {
  package: PackageView;
  reason: string;
}

export interface OfferView {
  id: UUID;
  title: string;
  description: string | null;
  terms: string | null;
  points_cost: number | null;
  cashback_percent: number | null;
  cashback_cap: number | null;
  min_recharge: number | null;
  package: PackageView | null;
  ends_on: DateString | null;
}

/** `GET /api/me/offers`. */
export interface OffersAndPoints {
  reward_points: number;
  offers: OfferView[];
}

/** `GET /api/me/cases` item. */
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

export type PortalCaseCategory =
  | 'recharge_not_credited'
  | 'unexpected_deduction'
  | 'package_activation'
  | 'network_issue'
  | 'billing'
  | 'other';

/** `POST /api/me/cases` body. `request_id` makes a retried submit idempotent. */
export interface PortalCaseCreate {
  category: PortalCaseCategory;
  /** 10–1000 characters after trimming. */
  description: string;
  priority?: CasePriority;
  request_id: UUID;
}

/** `GET /api/me/network` item. */
export interface IncidentView {
  district: string;
  area: string;
  kind: IncidentKind;
  status: IncidentStatus;
  message: string;
  starts_at: DateTimeString;
  ends_at: DateTimeString | null;
}

export interface PortalPurchase {
  kind: 'purchase';
  package_code: string;
  pay_from: TxnChannel;
}

export interface PortalRecharge {
  kind: 'recharge';
  amount: number;
  channel: TxnChannel;
  target_msisdn?: string | null;
}

export interface PortalRedeem {
  kind: 'redeem';
  offer_id: UUID;
}

/** The action a portal form starts and later confirms with the OTP (discriminated on `kind`). */
export type PortalAction = PortalPurchase | PortalRecharge | PortalRedeem;

/** The simulated SMS carrying the OTP. */
export interface OtpSms {
  code: string;
  to: string;
  expires_at: DateTimeString;
}

/** `POST /api/me/actions/start`. */
export interface ActionStart {
  action_id: UUID;
  kind: PortalActionKind;
  title: string;
  amount: number | null;
  pay_from: string | null;
  target: string | null;
  points_cost: number | null;
  /** Reward points a recharge will earn (1 per full ৳10), else null. */
  points_earned: number | null;
  expires_at: DateTimeString;
  otp: OtpSms;
}

/** `POST /api/me/actions/{action_id}/confirm`. */
export interface ActionResult {
  kind: PortalActionKind;
  ref: string;
  main_balance: number | null;
  postpaid_due: number | null;
  reward_points: number | null;
  /** Reward points the recharge earned, else null. */
  points_earned: number | null;
}

export type NotificationKind = 'pack_expiring' | 'low_balance' | 'low_data' | 'case_update';

/** One proactive nudge (`GET /api/me/notifications`); `payload` keys depend on `kind`. */
export interface NotificationView {
  id: UUID;
  kind: NotificationKind;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  created_at: DateTimeString;
  read_at: DateTimeString | null;
}

export interface NotificationList {
  unread: number;
  items: NotificationView[];
}
