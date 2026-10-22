import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomAgentDispatch, RoomConfiguration } from '@livekit/protocol';

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
// real estate agent worker gets explicitly dispatched into rooms this route creates.
const AGENT_NAME = process.env.AGENT_NAME || 'real_estate_agent';

// don't cache the results
export const revalidate = 0;

export async function POST(req: Request) {
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

    // Otherwise, explicitly dispatch the real estate agent into a fresh room,
    // tagged as an inbound customer chat session (as opposed to the outbound
    // cold-call sessions the scheduler dispatches separately). The browser's
    // anonymous visitor id (sent as a participant attribute by useSession) goes
    // into that metadata, so the agent stores it on the conversation row and
    // the chat widget can list this browser's earlier conversations. It is
    // deliberately not put into the token's own attributes.
    if (!existingRoomName) {
      const visitorId = parseVisitorId(body?.participant_attributes?.visitor_id);
      const metadata = JSON.stringify({
        channel: 'inbound_chat',
        ...(visitorId ? { visitor_id: visitorId } : {}),
      });
      if (roomConfig.agents.length === 0) {
        roomConfig.agents.push(new RoomAgentDispatch({ agentName: AGENT_NAME, metadata }));
      } else {
        // useSession adds a bare dispatch when the app config names the agent.
        for (const agent of roomConfig.agents) {
          if (!agent.metadata) agent.metadata = metadata;
        }
      }
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

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** The visitor id if it's a well-formed UUID, else null (the session just isn't listed). */
function parseVisitorId(value: unknown): string | null {
  return typeof value === 'string' && UUID_PATTERN.test(value) ? value.toLowerCase() : null;
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
