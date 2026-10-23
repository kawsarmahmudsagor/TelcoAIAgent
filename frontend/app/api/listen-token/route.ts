import { type NextRequest, NextResponse } from 'next/server';
import { AccessToken, type VideoGrant } from 'livekit-server-sdk';
import { isAdminSession } from '@/lib/admin-session';

// Dev-only helper: issues a join token for an EXISTING room by name (e.g. a
// cold-call room the scheduler already created), so the dashboard can be used
// to listen in on / talk back as a stand-in for the client during testing.
// Unlike /api/token, this never adds a RoomAgentDispatch -- the room already
// has its agent from the scheduler's dispatch, and re-declaring agents on a
// join token risks a second, redundant dispatch.

const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;

export const revalidate = 0;

export async function POST(req: NextRequest) {
  if (process.env.NODE_ENV !== 'development' && process.env.IS_VERCEL_PREVIEW !== 'true') {
    return new NextResponse('This dev-only listen endpoint is disabled outside development.', {
      status: 403,
    });
  }

  // This token is the listen-in credential for any existing room: admins only.
  if (!(await isAdminSession(req))) {
    return new NextResponse('Listening in requires an admin session.', {
      status: 403,
      headers: { 'Cache-Control': 'no-store' },
    });
  }

  try {
    if (!LIVEKIT_URL || !API_KEY || !API_SECRET) {
      throw new Error('Call server env vars are not configured');
    }

    const body = await req.json();
    const roomName = typeof body?.room_name === 'string' ? body.room_name.trim() : '';
    if (!roomName) {
      return new NextResponse('room_name is required', { status: 400 });
    }

    const identity = `dashboard-listener-${Math.floor(Math.random() * 10_000)}`;
    const at = new AccessToken(API_KEY, API_SECRET, { identity, ttl: '30m' });
    const grant: VideoGrant = {
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canPublishData: true,
      canSubscribe: true,
    };
    at.addGrant(grant);

    return NextResponse.json(
      { serverUrl: LIVEKIT_URL, roomName, participantToken: await at.toJwt() },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}
