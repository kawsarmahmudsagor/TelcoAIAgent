import type { DateTimeString, UUID } from './common';

export type BookingChannel = 'inbound_chat' | 'outbound_coldcall' | 'dashboard';

export type BookingStatus = 'proposed' | 'confirmed' | 'cancelled';

export type InviteRecipientType = 'client' | 'ceo';

export type InviteStatus = 'mock_sent' | 'failed';

export interface MeetingInvite {
  id: UUID;
  recipient_type: InviteRecipientType;
  recipient_email: string;
  subject: string;
  body: string;
  sent_status: InviteStatus;
  sent_at: DateTimeString | null;
}

export interface Booking {
  id: UUID;
  client_id: UUID;
  property_id: UUID | null;
  channel: BookingChannel;
  proposed_datetime: DateTimeString;
  status: BookingStatus;
  call_schedule_id: UUID | null;
  created_at: DateTimeString;
  updated_at: DateTimeString;
  /** The booking's client; viewings are booked with a name and phone number. */
  client_name: string | null;
  client_phone: string | null;
}

export interface BookingDetail extends Booking {
  invites: MeetingInvite[];
}

/** `POST /api/bookings`: a viewing booked by hand for an existing lead. */
export interface BookingCreate {
  client_id: UUID;
  property_id?: UUID | null;
  proposed_datetime: DateTimeString;
}

export interface BookingListParams {
  limit?: number;
  offset?: number;
}
