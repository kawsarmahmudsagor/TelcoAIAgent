import { apiFetch, qs } from './api-client';
import type {
  AccountSummary,
  ActionResult,
  ActionStart,
  CaseView,
  IncidentView,
  NotificationList,
  NotificationView,
  OffersAndPoints,
  PackageKind,
  PackageView,
  PersonaCard,
  PortalAction,
  PortalCaseCreate,
  PortalMe,
  Recommendation,
  TransactionParams,
  TransactionView,
  UsageBreakdown,
} from './types/portal';

const get = <T>(path: string) => apiFetch<T>(path);
const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, {
    method: 'POST',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });

/**
 * The customer portal's FastAPI calls. The signed-in subscriber comes from the httponly
 * `portal_session` cookie set by `login`; failures throw `ApiError` with `.code` from
 * `detail.code` (e.g. `otp_invalid`, `insufficient_balance`).
 */
export const portalApi = {
  /** Unauthenticated: the five demo personas. */
  personas: () => get<PersonaCard[]>('/api/demo/personas'),
  /** Signs in as a persona (sets the `portal_session` cookie). */
  login: (msisdn: string) => post<PortalMe>('/api/demo/login', { msisdn }),
  logout: () => post<{ ok: boolean }>('/api/demo/logout'),
  /** Unauthenticated: the active pack catalog, for the public home page. */
  catalog: (kind?: PackageKind) => get<PackageView[]>(`/api/catalog/packages${qs({ kind })}`),

  me: () => get<PortalMe>('/api/me'),
  summary: () => get<AccountSummary>('/api/me/summary'),
  usage: (periodDays: number) =>
    get<UsageBreakdown>(`/api/me/usage${qs({ period_days: periodDays })}`),
  transactions: (params?: TransactionParams) =>
    get<TransactionView[]>(`/api/me/transactions${qs(params)}`),
  packages: (kind?: PackageKind) => get<PackageView[]>(`/api/me/packages${qs({ kind })}`),
  recommendations: () => get<Recommendation[]>('/api/me/recommendations'),
  offers: () => get<OffersAndPoints>('/api/me/offers'),
  cases: () => get<CaseView[]>('/api/me/cases'),
  createCase: (body: PortalCaseCreate) => post<CaseView>('/api/me/cases', body),
  network: () => get<IncidentView[]>('/api/me/network'),

  notifications: () => get<NotificationList>('/api/me/notifications'),
  markNotificationRead: (id: string) =>
    post<NotificationView>(`/api/me/notifications/${encodeURIComponent(id)}/read`),
  markAllNotificationsRead: () => post<{ updated: number }>('/api/me/notifications/read-all'),

  /** Validates the action and sends the OTP (returned in `otp` for the demo SMS toast). */
  startAction: (action: PortalAction) => post<ActionStart>('/api/me/actions/start', action),
  /** Runs the action if `code` matches; send the same `action` that was started. */
  confirmAction: (actionId: string, action: PortalAction, code: string) =>
    post<ActionResult>(`/api/me/actions/${actionId}/confirm`, { action, code }),
};
