import { type NextRequest, NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomAgentDispatch, RoomConfiguration } from '@livekit/protocol';
import { buildDispatchMetadata } from '@/lib/agent-dispatch';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// NOTE: you are expected to define the following environment variables in `.env.local`:
const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
// Must match app.config.Settings.agent_name on the backend — this is how the
// telco agent worker gets explicitly dispatched into rooms this route creates.
const AGENT_NAME = process.env.AGENT_NAME || 'telco_agent';
// Server-to-server: this route asks FastAPI directly who the portal cookie belongs to.
const FASTAPI_INTERNAL_URL = process.env.FASTAPI_INTERNAL_URL || 'http://localhost:8011';
const PORTAL_COOKIE = 'portal_session';

// don't cache the results
export const revalidate = 0;

export async function POST(req: NextRequest) {
  // make an exception for the vercel preview environment
  if (process.env.NODE_ENV !== 'development' && process.env.IS_VERCEL_PREVIEW !== 'true') {
    throw new Error(
      'THIS API ROUTE IS INSECURE. DO NOT USE THIS ROUTE IN PRODUCTION WITHOUT AN AUTHENTICATION LAYER.'
    );
  }

  try {
    if (LIVEKIT_URL === undefined) {
      throw new Error('LIVEKIT_URL is not defined');
    }
    if (API_KEY === undefined) {
      throw new Error('LIVEKIT_API_KEY is not defined');
    }
    if (API_SECRET === undefined) {
      throw new Error('LIVEKIT_API_SECRET is not defined');
    }

    // Parse room config from request body.
    const body = await req.json();
    const roomConfig = body?.room_config
      ? RoomConfiguration.fromJson(body.room_config, { ignoreUnknownFields: true })
      : new RoomConfiguration();

    // A `room_name` in the request means the caller wants to join a room that
    // already exists (e.g. the admin dashboard jumping straight to the live
    // conversation UI for a scheduled cold call the moment it fires) --
    // that room already has its agent dispatched by the scheduler with its
    // own outbound_coldcall metadata, so don't add a second, redundant
    // dispatch on top of it.
    const existingRoomName =
      typeof body?.room_name === 'string' && body.room_name.trim() ? body.room_name.trim() : null;

    // Every agent dispatch carries server-built metadata, tagged as an inbound customer chat
    // (as opposed to the outbound cold-call sessions the scheduler dispatches separately).
    // Whatever metadata the client sent is discarded: `subscriber_id` comes only from the
    // `portal_session` cookie as verified by FastAPI, so a guest (no cookie or a rejected one)
    // gets none. The browser's anonymous visitor id (a participant attribute set by useSession)
    // and the nudge being answered (`nudge_id`) are passed through only when they are UUIDs.
    const subscriberId = await resolveSubscriberId(req);
    const metadata = buildDispatchMetadata(subscriberId, {
      visitorId: body?.participant_attributes?.visitor_id,
      nudgeId: body?.nudge_id,
    });
    for (const agent of roomConfig.agents) {
      // useSession adds a bare dispatch when the app config names the agent.
      agent.metadata = metadata;
    }
    // A fresh room gets exactly one dispatch of the telco agent; an existing room already has
    // its agent.
    if (!existingRoomName && roomConfig.agents.length === 0) {
      roomConfig.agents.push(new RoomAgentDispatch({ agentName: AGENT_NAME, metadata }));
    }

    // Generate participant token
    const participantName = 'user';
    const participantIdentity = `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
    const roomName =
      existingRoomName ?? `voice_assistant_room_${Math.floor(Math.random() * 10_000)}`;

    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: participantName },
      roomName,
      roomConfig
    );

    // Return connection details
    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName,
      participantToken,
    };
    const headers = new Headers({
      'Cache-Control': 'no-store',
    });
    return NextResponse.json(data, { headers });
  } catch (error) {
    if (error instanceof Error) {
      console.error(error);
      return new NextResponse(error.message, { status: 500 });
    }
  }
}

/**
 * The signed-in customer's subscriber id, verified by FastAPI's `GET /api/me` against the
 * `portal_session` cookie; null (a guest) without the cookie or on any non-200 answer.
 */
async function resolveSubscriberId(req: NextRequest): Promise<string | null> {
  const session = req.cookies.get(PORTAL_COOKIE)?.value;
  if (!session) return null;
  try {
    const res = await fetch(`${FASTAPI_INTERNAL_URL}/api/me`, {
      headers: { cookie: `${PORTAL_COOKIE}=${session}` },
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });
    if (res.status !== 200) return null;
    const me = (await res.json()) as { subscriber_id?: unknown };
    return typeof me.subscriber_id === 'string' ? me.subscriber_id : null;
  } catch (error) {
    console.error('Could not resolve the portal session; dispatching as a guest.', error);
    return null;
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig: RoomConfiguration | undefined
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
    // The public property page sets a `viewing_property_id` attribute so the agent knows which
    // listing the customer has open.
    canUpdateOwnMetadata: true,
  };
  at.addGrant(grant);

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}
