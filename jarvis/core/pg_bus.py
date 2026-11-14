"""PostgreSQL LISTEN/NOTIFY async pub/sub bus with in-memory fallback for SQLite test mode."""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Set

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

logger = logging.getLogger(__name__)

PG_CHANNEL = "jarvis_events"
EventCallback = Callable[[Dict[str, Any]], Awaitable[None]]


class PostgresEventBus:
    """
    Real-time pub/sub bus powered by PostgreSQL LISTEN/NOTIFY.
    Falls back to an in-process async dispatch if PostgreSQL is unavailable
    (e.g. SQLite unit tests).
    """

    def __init__(self, dsn: Optional[str] = None, channel: str = PG_CHANNEL):
        self.dsn = dsn
        self.channel = channel
        self._listen_conn: Optional[Any] = None
        self._callbacks: Set[EventCallback] = set()
        self._pg_active = False
        self._lock = asyncio.Lock()

    def subscribe(self, callback: EventCallback) -> None:
        self._callbacks.add(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        self._callbacks.discard(callback)

    async def start(self, dsn: Optional[str] = None) -> None:
        async with self._lock:
            if dsn:
                self.dsn = dsn
            if not self.dsn or not self.dsn.startswith("postgres") or asyncpg is None:
                self._pg_active = False
                return
            if self._listen_conn is not None and not self._listen_conn.is_closed():
                return
            try:
                self._listen_conn = await asyncpg.connect(self.dsn)
                await self._listen_conn.add_listener(self.channel, self._on_pg_notify)
                self._pg_active = True
                logger.info("PostgresEventBus listening on channel '%s'", self.channel)
            except Exception as exc:
                logger.warning("PostgresEventBus falling back to in-memory dispatch: %s", exc)
                self._pg_active = False
                self._listen_conn = None

    async def stop(self) -> None:
        async with self._lock:
            if self._listen_conn is not None:
                try:
                    await self._listen_conn.remove_listener(self.channel, self._on_pg_notify)
                    await self._listen_conn.close()
                except Exception:
                    pass
                self._listen_conn = None
            self._pg_active = False

    def _on_pg_notify(self, connection: Any, pid: int, channel: str, payload: str) -> None:
        try:
            data = json.loads(payload)
        except Exception:
            data = {"event": "raw", "data": {"payload": payload}}
        asyncio.create_task(self._dispatch(data))

    async def _dispatch(self, event_dict: Dict[str, Any]) -> None:
        for cb in list(self._callbacks):
            try:
                await cb(event_dict)
            except Exception as exc:
                logger.debug("Event callback failed: %s", exc)

    async def publish(self, event: str, event_type: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        payload_dict: Dict[str, Any] = {
            "event": event,
            "type": event_type,
            "data": data or {},
        }
        payload_str = json.dumps(payload_dict, default=str)

        if self._pg_active and self._listen_conn is not None and not self._listen_conn.is_closed():
            try:
                await self._listen_conn.execute("SELECT pg_notify($1, $2)", self.channel, payload_str)
                return
            except Exception as exc:
                logger.warning("pg_notify failed, dispatching in-memory: %s", exc)

        await self._dispatch(payload_dict)
