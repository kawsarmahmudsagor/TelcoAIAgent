import logging

from livekit.api import DeleteRoomRequest, LiveKitAPI

from app.config import get_settings

logger = logging.getLogger("livekit_rooms")


async def delete_room(name: str) -> None:
    """Best-effort room teardown. Deleting a room that nobody has joined yet
    disconnects the agent job still waiting in it, so it exits instead of
    idling until its wait times out. Failures (room already gone,
    LiveKit unreachable) are logged, not raised -- the call's status is the
    source of truth, not the room."""
    settings = get_settings()
    lk = LiveKitAPI(
        url=settings.livekit_url, api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret
    )
    try:
        await lk.room.delete_room(DeleteRoomRequest(room=name))
    except Exception:
        logger.warning("failed to delete livekit room %s", name, exc_info=True)
    finally:
        await lk.aclose()
