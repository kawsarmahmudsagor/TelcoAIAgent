import { del, get, patch, post, qs } from './api-client';
import type {
  AdminCase,
  AdminOffer,
  AdminPackage,
  AiMonitor,
  AiMonitorWindow,
  CaseList,
  CaseListParams,
  CaseStats,
  IncidentAdminView,
  IncidentCreate,
  NetworkOverview,
  NudgeRunResult,
  OfferCreate,
  OfferPatch,
  Overview,
  SubscriberDetail,
  SubscriberList,
  SubscriberListParams,
  TransactionList,
  TransactionListParams,
  TransactionStats,
} from './types/admin';
import type { CaseStatus } from './types/portal';

/**
 * The admin portal's FastAPI calls (`/api/admin/*`). They authenticate with the httponly admin
 * `session` cookie; a customer `portal_session` gets 401. Failures throw `ApiError`.
 */
export const adminApi = {
  overview: () => get<Overview>('/api/admin/overview'),

  subscribers: (params?: SubscriberListParams) =>
    get<SubscriberList>(`/api/admin/subscribers${qs(params)}`),
  subscriber: (id: string) => get<SubscriberDetail>(`/api/admin/subscribers/${id}`),

  transactions: (params?: TransactionListParams) =>
    get<TransactionList>(`/api/admin/transactions${qs(params)}`),
  transactionStats: () => get<TransactionStats>('/api/admin/transactions/stats'),

  aiMonitor: (window: AiMonitorWindow = '24h') =>
    get<AiMonitor>(`/api/admin/ai-monitor${qs({ window })}`),

  cases: (params?: CaseListParams) => get<CaseList>(`/api/admin/cases${qs(params)}`),
  caseStats: () => get<CaseStats>('/api/admin/cases/stats'),
  /** Changes a case's status and nudges its subscriber (`case_update`). */
  setCaseStatus: (ref: string, status: CaseStatus) =>
    patch<AdminCase>(`/api/admin/cases/${encodeURIComponent(ref)}`, { status }),

  network: () => get<NetworkOverview>('/api/admin/network'),
  createIncident: (body: IncidentCreate) =>
    post<IncidentAdminView>('/api/admin/network/incidents', body),
  resolveIncident: (id: string) =>
    post<IncidentAdminView>(`/api/admin/network/incidents/${id}/resolve`),

  /** Runs the nudge sweep now instead of waiting for the 15-minute schedule. */
  runNudges: () => post<NudgeRunResult>('/api/admin/nudges/run'),

  packages: () => get<AdminPackage[]>('/api/admin/packages'),
  offers: () => get<AdminOffer[]>('/api/admin/offers'),
  createOffer: (body: OfferCreate) => post<AdminOffer>('/api/admin/offers', body),
  updateOffer: (id: string, body: OfferPatch) => patch<AdminOffer>(`/api/admin/offers/${id}`, body),
  deleteOffer: (id: string) => del(`/api/admin/offers/${id}`),
};
