"""Registers the Twilio Elastic SIP Trunk with LiveKit as an outbound trunk and
prints its id for SIP_OUTBOUND_TRUNK_ID. Safe to re-run: an existing trunk with
the same name is reused, not duplicated.

Requires livekit-server running with Redis and livekit-sip attached (see
docs/telephony-setup.md), plus TWILIO_* values in .env.

    uv run python -m app.scripts.create_sip_trunk
"""

import asyncio
import sys

from livekit import api

from app.config import get_settings

TRUNK_NAME = "twilio-outbound"


async def main() -> int:
    settings = get_settings()
    missing = [
        name
        for name, value in {
            "TWILIO_PHONE_NUMBER": settings.twilio_phone_number,
            "TWILIO_SIP_TERMINATION_URI": settings.twilio_sip_termination_uri,
            "TWILIO_SIP_USERNAME": settings.twilio_sip_username,
            "TWILIO_SIP_PASSWORD": settings.twilio_sip_password,
        }.items()
        if not value
    ]
    if missing:
        print(f"Set these in .env first: {', '.join(missing)}", file=sys.stderr)
        return 1

    lk = api.LiveKitAPI(
        url=settings.livekit_url, api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret
    )
    try:
        existing = await lk.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
        for trunk in existing.items:
            if trunk.name == TRUNK_NAME:
                print(f"Trunk already exists. SIP_OUTBOUND_TRUNK_ID={trunk.sip_trunk_id}")
                return 0

        trunk = await lk.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(
                trunk=api.SIPOutboundTrunkInfo(
                    name=TRUNK_NAME,
                    address=settings.twilio_sip_termination_uri,
                    numbers=[settings.twilio_phone_number],
                    auth_username=settings.twilio_sip_username,
                    auth_password=settings.twilio_sip_password,
                )
            )
        )
        print(f"Created trunk. SIP_OUTBOUND_TRUNK_ID={trunk.sip_trunk_id}")
        return 0
    finally:
        await lk.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
