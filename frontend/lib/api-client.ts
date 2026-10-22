import type {
  AgentConfig,
  AgentConfigOptions,
  AgentConfigUpdate,
  Booking,
  BookingCreate,
  BookingDetail,
  BookingListParams,
  BulkDeleteResult,
  CallDeclineReason,
  CallScheduleCreate,
  CallScheduleEntry,
  CallScheduleOut,
  CallScheduleUpdate,
  Client,
  ClientCreate,
  ClientUpdate,
  ConversationDetail,
  ConversationListItem,
  ConversationListParams,
  ConversationPage,
  ConversationSeries,
  CreateSourceResponse,
  DashboardSummary,
  EmbeddingJob,
  EmbeddingJobListParams,
  ImportClientsResult,
  IncomingCall,
  LeadListParams,
  LinkSourceCreate,
  MeResponse,
  Offer,
  OfferCreate,
  OfferUpdate,
  OkResponse,
  Property,
  PropertyCreate,
  PropertyListParams,
  PropertyUpdate,
  PublicListing,
  PublicListingParams,
  PublicOffer,
  RagSearchRequest,
  RagSearchResponse,
  RagSourceDetail,
  RagSourceList,
  RagSourceListParams,
  RagStatus,
  RecentBooking,
  ReindexAllResponse,
  ScheduleLead,
  ScheduleListParams,
  SeriesRange,
  TextSourceCreate,
  UUID,
  VoicePreviewRequest,
} from './types';

// Re-exported so existing `import { type Client, api } from '@/lib/api-client'` keeps working.
export type * from './types';

// Default: same-origin `/backend`, proxied to FastAPI by next.config.ts rewrites,
// so the dashboard also works through a Cloudflare tunnel (one hostname, no CORS).
// NEXT_PUBLIC_FASTAPI_URL still overrides it for a directly-reachable backend.
const FASTAPI_URL = process.env.NEXT_PUBLIC_FASTAPI_URL || '/backend';

export class ApiError extends Error {
  status: number;
  /** Machine-readable reason when FastAPI sends `{"detail": {"code", "message"}}` (e.g. `otp_invalid`). */
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** An ApiError built from a failed response: its message, plus `detail.code` when present. */
async function apiError(res: Response): Promise<ApiError> {
  const body = await res.text();
  return new ApiError(res.status, errorMessage(res, body), errorCode(body));
}

function errorCode(body: string): string | undefined {
  try {
    const { detail } = JSON.parse(body);
    if (detail && typeof detail === 'object' && typeof detail.code === 'string') return detail.code;
  } catch {
    // not JSON
  }
  return undefined;
}

// FastAPI errors are `{"detail": "..."}` or `{"detail": {"code", "message"}}` -- show that
// message, not the raw JSON.
function errorMessage(res: Response, body: string): string {
  try {
    const { detail } = JSON.parse(body);
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
      return detail.message;
    }
    // Pydantic validation: [{loc: ['body', 'field'], msg: '...'}, ...]
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((item: { loc?: (string | number)[]; msg?: string }) => {
          const field = item.loc?.filter((part) => part !== 'body').join('.');
          return field ? `${field}: ${item.msg}` : (item.msg ?? '');
        })
        .join('; ');
    }
  } catch {
    // not JSON -- fall through to the raw body
  }
  // An HTML error page (e.g. Cloudflare's 502 when the backend is unreachable) is no message.
  if (/^\s*</.test(body)) {
    return res.status === 502 || res.status === 504
      ? 'The server is unreachable right now. Try again in a moment.'
      : `The server answered ${res.status} ${res.statusText}`.trim();
  }
  return body || res.statusText;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${FASTAPI_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      // Only JSON bodies: a FormData body needs the browser-set multipart boundary.
      ...(typeof init?.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw await apiError(res);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

type QueryValue = string | number | boolean | null | undefined;

/** `?a=1&b=x` from the defined, non-null params ('' when none). */
export function qs(params?: object): string {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params) as [string, QueryValue][]) {
    if (value !== undefined && value !== null) search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

/** POST a JSON body and get binary back (e.g. audio). */
async function postForBlob(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`${FASTAPI_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await apiError(res);
  }
  return res.blob();
}

const get = <T>(path: string) => apiFetch<T>(path);
const post = <T>(path: string, body?: unknown) =>
  apiFetch<T>(path, {
    method: 'POST',
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
const patch = <T>(path: string, body: unknown) =>
  apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const del = (path: string) => apiFetch<void>(path, { method: 'DELETE' });

const auth = {
  login: (username: string, password: string) =>
    post<OkResponse>('/api/auth/login', { username, password }),
  logout: () => post<OkResponse>('/api/auth/logout'),
  me: () => get<MeResponse>('/api/auth/me'),
};

const leads = {
  list: (params?: LeadListParams) => get<Client[]>(`/api/leads${qs(params)}`),
  get: (id: UUID) => get<Client>(`/api/leads/${id}`),
  create: (payload: ClientCreate) => post<Client>('/api/leads', payload),
  update: (id: UUID, payload: ClientUpdate) => patch<Client>(`/api/leads/${id}`, payload),
  /** Upload an .xlsx of clients. */
  import: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch<ImportClientsResult>('/api/import/clients', {
      method: 'POST',
      body: formData,
    });
  },
};

const schedule = {
  list: (params?: ScheduleListParams) => get<CallScheduleEntry[]>(`/api/schedule${qs(params)}`),
  /** Every lead a call can be scheduled for, with their upcoming viewing if any. */
  leads: () => get<ScheduleLead[]>('/api/schedule/leads'),
  create: (payload: CallScheduleCreate) => post<CallScheduleOut>('/api/schedule', payload),
  update: (id: UUID, payload: CallScheduleUpdate) =>
    patch<CallScheduleOut>(`/api/schedule/${id}`, payload),
  delete: (id: UUID) => del(`/api/schedule/${id}`),
  /** Ends a ringing or live call (browser or phone). */
  hangUp: (id: UUID) => post<CallScheduleOut>(`/api/schedule/${id}/hangup`),
  /** Browser calls only; 409 for phone calls. */
  incoming: (id: UUID) => get<IncomingCall>(`/api/schedule/${id}/incoming`),
  decline: (id: UUID, reason: CallDeclineReason) =>
    post<CallScheduleOut>(`/api/schedule/${id}/decline`, { reason }),
};

const bookings = {
  list: (params?: BookingListParams) => get<Booking[]>(`/api/bookings${qs(params)}`),
  get: (id: UUID) => get<BookingDetail>(`/api/bookings/${id}`),
  /** Books a viewing by hand; 400 for a past time or one outside viewing hours. */
  create: (payload: BookingCreate) => post<Booking>('/api/bookings', payload),
};

const properties = {
  list: (params?: PropertyListParams) => get<Property[]>(`/api/properties${qs(params)}`),
  // No GET /api/properties/{id} on the backend: find it in the list.
  get: async (id: UUID) => {
    const all = await get<Property[]>(`/api/properties${qs({ limit: 1000 })}`);
    const found = all.find((property) => property.id === id);
    if (!found) throw new ApiError(404, 'Property not found');
    return found;
  },
  create: (payload: PropertyCreate) => post<Property>('/api/properties', payload),
  update: (id: UUID, payload: PropertyUpdate) => patch<Property>(`/api/properties/${id}`, payload),
  /** Soft delete: sets is_active = false. */
  delete: (id: UUID) => del(`/api/properties/${id}`),
};

const offers = {
  list: () => get<Offer[]>('/api/offers'),
  get: (id: UUID) => get<Offer>(`/api/offers/${id}`),
  create: (payload: OfferCreate) => post<Offer>('/api/offers', payload),
  update: (id: UUID, payload: OfferUpdate) => patch<Offer>(`/api/offers/${id}`, payload),
  /** Hard delete. */
  delete: (id: UUID) => del(`/api/offers/${id}`),
};

const agentConfig = {
  get: () => get<AgentConfig>('/api/agent-config'),
  update: (payload: AgentConfigUpdate) => patch<AgentConfig>('/api/agent-config', payload),
  options: () => get<AgentConfigOptions>('/api/agent-config/options'),
  resetPrompt: () => post<AgentConfig>('/api/agent-config/reset-prompt'),
  /** mp3 of a sample line in the given voice. Spends the provider's credits. */
  previewVoice: (payload: VoicePreviewRequest) =>
    postForBlob('/api/agent-config/voice-preview', payload),
  /** Starts a background re-embed; poll `get()` for embedding_migration_status. */
  migrateEmbedding: (embedding_model: string) =>
    post<AgentConfig>('/api/agent-config/migrate-embedding', { embedding_model }),
};

const conversations = {
  list: (params?: ConversationListParams) =>
    get<ConversationPage>(`/api/conversations${qs(params)}`),
  get: (id: UUID) => get<ConversationDetail>(`/api/conversations/${id}`),
  delete: (id: UUID) => del(`/api/conversations/${id}`),
  bulkDelete: (ids: UUID[]) => post<BulkDeleteResult>('/api/conversations/bulk-delete', { ids }),
};

const dashboard = {
  summary: () => get<DashboardSummary>('/api/dashboard/summary'),
  conversationSeries: (range: SeriesRange = '7d') =>
    get<ConversationSeries>(`/api/dashboard/conversation-series${qs({ range })}`),
  recentConversations: (limit?: number) =>
    get<ConversationListItem[]>(`/api/dashboard/recent-conversations${qs({ limit })}`),
  recentBookings: (limit?: number) =>
    get<RecentBooking[]>(`/api/dashboard/recent-bookings${qs({ limit })}`),
  ragStatus: () => get<RagStatus>('/api/dashboard/rag-status'),
};

const rag = {
  sources: (params?: RagSourceListParams) => get<RagSourceList>(`/api/rag/sources${qs(params)}`),
  getSource: (id: UUID) => get<RagSourceDetail>(`/api/rag/sources/${id}`),
  deleteSource: (id: UUID) => del(`/api/rag/sources/${id}`),
  /** One file per call (backend takes a single `file` field). */
  uploadDocument: (file: File, name?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);
    return apiFetch<CreateSourceResponse>('/api/rag/sources/documents', {
      method: 'POST',
      body: formData,
    });
  },
  uploadDocuments: (files: File[]) => Promise.all(files.map((file) => rag.uploadDocument(file))),
  addLink: (payload: LinkSourceCreate) =>
    post<CreateSourceResponse>('/api/rag/sources/links', payload),
  addText: (payload: TextSourceCreate) =>
    post<CreateSourceResponse>('/api/rag/sources/text', payload),
  /** Creates the property-listings source on first use and queues a sync. */
  syncProperties: () => post<CreateSourceResponse>('/api/rag/sources/properties/sync'),
  reindexSource: (id: UUID) => post<CreateSourceResponse>(`/api/rag/sources/${id}/reindex`),
  reindexAll: () => post<ReindexAllResponse>('/api/rag/reindex-all'),
  jobs: (params?: EmbeddingJobListParams) => get<EmbeddingJob[]>(`/api/rag/jobs${qs(params)}`),
  retryJob: (id: UUID) => post<EmbeddingJob>(`/api/rag/jobs/${id}/retry`),
  search: (payload: RagSearchRequest) => post<RagSearchResponse>('/api/rag/search', payload),
};

const publicApi = {
  /** Unauthenticated. */
  listings: (params?: PublicListingParams) =>
    get<PublicListing[]>(`/api/public/listings${qs(params)}`),
  /** Unauthenticated: live offers. */
  offers: () => get<PublicOffer[]>('/api/public/offers'),
};

export const api = {
  // Nested, per domain.
  auth,
  leads: Object.assign(
    // Legacy: `api.leads()` lists leads (args ignored, so it is safe as a callback).
    () => leads.list(),
    leads
  ),
  schedule: Object.assign(
    // Legacy: `api.schedule()` lists schedule entries.
    () => schedule.list(),
    schedule
  ),
  bookings: Object.assign(
    // Legacy: `api.bookings()` lists bookings.
    () => bookings.list(),
    bookings
  ),
  properties,
  offers,
  agentConfig,
  conversations,
  dashboard,
  rag,
  public: publicApi,

  // Legacy flat names, kept for existing pages.
  login: auth.login,
  logout: auth.logout,
  me: auth.me,
  dashboardSummary: dashboard.summary,
  createLead: leads.create,
  createSchedule: schedule.create,
  deleteSchedule: schedule.delete,
  scheduleLeads: schedule.leads,
  hangUpCall: schedule.hangUp,
  incomingCall: schedule.incoming,
  declineCall: schedule.decline,
  importClients: leads.import,
};
