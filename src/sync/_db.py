"""Shared DB connection helper that handles special characters in passwords."""
from __future__ import annotations
from urllib.parse import unquote


def parse_db_url(url: str) -> dict:
    """
    Parse a DATABASE_URL without urlparse so special chars in passwords work.
    Handles both postgresql:// and postgresql+asyncpg:// schemes.
    Returns kwargs suitable for asyncpg.connect().
    """
    # Strip SQLAlchemy dialect prefix
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break

    # Split credentials from host at the rightmost @
    at = url.rindex("@")
    credentials = url[:at]
    rest = url[at + 1:]

    # Split user:password (first colon only)
    colon = credentials.index(":")
    user = credentials[:colon]
    password = unquote(credentials[colon + 1:])

    # Split host:port/database
    slash = rest.index("/")
    host_port = rest[:slash]
    database = rest[slash + 1:]

    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 5432

    return {"host": host, "port": port, "user": user, "password": password, "database": database}
