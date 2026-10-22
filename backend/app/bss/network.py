from datetime import datetime, timedelta

from sqlalchemy import Select, func, select

from app.models.telco import IncidentStatus, NetworkIncident


def active_incidents_query(district: str, now: datetime) -> Select:
    """Incidents in force in `district` at `now`: not resolved, starting within
    the next day (so scheduled maintenance tomorrow shows), not yet ended.
    The one rule shared by account summaries and the network status check."""
    return select(NetworkIncident).where(
        func.lower(NetworkIncident.district) == district.lower(),
        NetworkIncident.status != IncidentStatus.resolved,
        NetworkIncident.starts_at <= now + timedelta(days=1),
        (NetworkIncident.ends_at.is_(None)) | (NetworkIncident.ends_at > now),
    )
