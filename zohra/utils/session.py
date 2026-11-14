"""Trading session detection (UTC)."""

from datetime import datetime, time

from zohra.core.enums import Session


def detect_session(dt: datetime = None) -> Session:
    """Classify current UTC session."""
    dt = dt or datetime.utcnow()
    t = dt.time()

    asia = time(0, 0) <= t < time(8, 0)
    london = time(8, 0) <= t < time(13, 0)
    overlap = time(13, 0) <= t < time(17, 0)
    ny = time(17, 0) <= t < time(22, 0)

    if overlap:
        return Session.OVERLAP
    if london:
        return Session.LONDON
    if ny:
        return Session.NEW_YORK
    if asia:
        return Session.ASIA
    return Session.OFF
