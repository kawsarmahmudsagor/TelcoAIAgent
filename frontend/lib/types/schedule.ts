import type { DateTimeString, UUID } from './common';
import type { Client } from './lead';

export type CallStatus =
  | 'pending'
  | 'dispatched'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'missed';

/** Backend `CallScheduleOut` (no embedded client). */
export interface CallScheduleOut {
  id: UUID;
  client_id: UUID;
  scheduled_at: DateTimeString;
  status: CallStatus;
  /** Set -> rings this phone (E.164) instead of the browser incoming-call screen. */
  dial_number: string | null;
  livekit_room_name: string | null;
  dispatched_at: DateTimeString | null;
  answered_at: DateTimeString | null;
  completed_at: DateTimeString | null;
  outcome: string | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
}

/** Backend `CallScheduleWithClientOut`, as returned by `GET /api/schedule`. */
export interface CallScheduleEntry extends CallScheduleOut {
  client: Client;
  /**
   * Schedule list only: an open call whose lead has this viewing after the call time follows it
   * up; null = a cold call (or the call has finished). Decided again when the call starts.
   */
  viewing?: UpcomingViewing | null;
}

export interface IncomingCall extends CallScheduleEntry {
  agent_display_name: string;
  operator_name: string;
}

/** cancelled: the callee pressed Decline; missed: nobody answered in time. */
export type CallDeclineReason = 'cancelled' | 'missed';

export interface CallScheduleCreate {
  client_id: UUID;
  scheduled_at: DateTimeString;
  /** Phone number to ring; blank/omitted keeps the browser incoming-call flow. */
  dial_number?: string | null;
}

export interface CallScheduleUpdate {
  status?: CallStatus | null;
  scheduled_at?: DateTimeString | null;
}

/** The lead's next booked viewing. */
export interface UpcomingViewing {
  booking_id: UUID;
  when: DateTimeString;
  property_title: string | null;
}

/**
 * As returned by `GET /api/schedule/leads`: every lead, those with an upcoming viewing first
 * (soonest first, the call follows it up), then the rest by name (a plain cold call).
 */
export interface ScheduleLead {
  client: Client;
  viewing: UpcomingViewing | null;
}

export interface ScheduleListParams {
  call_status?: CallStatus;
  limit?: number;
  offset?: number;
}
