import { type NextRequest, NextResponse } from 'next/server';
import { RoomServiceClient } from 'livekit-server-sdk';
import { resolveSubscriberId } from '@/lib/portal-session';

const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;

export const revalidate = 0;

function reply(status: number, message: string) {
  return new NextResponse(message, { status, headers: { 'Cache-Control': 'no-store' } });
}

/**
 * Links a guest assistant session to the customer who just logged in, so the conversation carries
 * on (backend/app/agent/account_link.py). The subscriber comes only from the `portal_session`
 * cookie, verified by FastAPI. The room and the caller's identity must match a live participant:
 * both are random ids only that browser holds. The link is written to the room metadata with the
 * LiveKit server API, which browsers can't do (their tokens have no roomAdmin grant). A room that
 * already belongs to a customer is never moved to another.
 */
export async function POST(req: NextRequest) {
  if (!LIVEKIT_URL || !API_KEY || !API_SECRET) {
    return reply(500, 'LiveKit is not configured');
  }
  const body = await req.json().catch(() => null);
  const roomName = typeof body?.room_name === 'string' ? body.room_name : '';
  const identity = typeof body?.identity === 'string' ? body.identity : '';
  if (!roomName || !identity) return reply(400, 'room_name and identity are required');

  const subscriberId = await resolveSubscriberId(req);
  if (!subscriberId) return reply(401, 'Log in first');

  const rooms = new RoomServiceClient(LIVEKIT_URL.replace(/^ws/, 'http'), API_KEY, API_SECRET);
  try {
    const [room] = await rooms.listRooms([roomName]);
    if (!room) return reply(404, 'No such session');
    const participants = await rooms.listParticipants(roomName);
    if (!participants.some((p) => p.identity === identity)) return reply(404, 'No such session');

    const current = linkedSubscriber(room.metadata);
    if (current === subscriberId) return NextResponse.json({ linked: true });
    if (current) return reply(409, 'This session belongs to another account');

    await rooms.updateRoomMetadata(roomName, JSON.stringify({ subscriber_id: subscriberId }));
    return NextResponse.json({ linked: true });
  } catch (error) {
    console.error('Could not link the assistant session.', error);
    return reply(502, 'Could not reach the assistant');
  }
}

function linkedSubscriber(metadata: string | undefined): string | null {
  try {
    const parsed = metadata ? JSON.parse(metadata) : null;
    return typeof parsed?.subscriber_id === 'string' ? parsed.subscriber_id : null;
  } catch {
    return null;
  }
}
