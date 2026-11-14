"""Standalone native PostgreSQL (pgAdmin) database, role, and schema initializer for Jarvis."""

import os
import sys
from urllib.parse import urlparse, urlunparse

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    psycopg2 = None  # type: ignore

from jarvis.config import ADMIN_POSTGRES_URL, DEFAULT_POSTGRES_URL, load_config, load_dotenv_files
from jarvis.store import POSTGRES_DDL_STATEMENTS, ReminderStore

REQUIRED_TABLES = (
    "tasks",
    "action_logs",
    "weekly_routine",
    "alarms",
    "courses",
    "course_logs",
    "business_deliverables",
    "small_tasks",
)

FALLBACK_ADMIN_URLS = (
    ADMIN_POSTGRES_URL,
    "postgresql://postgres:hackathon@localhost:5432/postgres",
    "postgresql://gym:gym@localhost:5432/postgres",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)


def resolve_database_url(explicit_url: str | None = None) -> str:
    """Resolve DATABASE_URL from argument, .env / environment variable, or config.yaml."""
    load_dotenv_files()
    if explicit_url:
        return explicit_url
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    cfg = load_config()
    return cfg.get_database_url() or DEFAULT_POSTGRES_URL


def build_maintenance_url(database_url: str, maintenance_db: str = "postgres") -> tuple[str, str]:
    """Return (maintenance_url, target_db_name) from the configured DATABASE_URL."""
    parsed = urlparse(database_url)
    target_db = (parsed.path or "").lstrip("/") or "jarvis"
    maint_parsed = parsed._replace(path=f"/{maintenance_db}")
    return urlunparse(maint_parsed), target_db


def _ensure_jarvis_role_and_db(conn, target_db: str) -> None:
    """Ensure the `jarvis` role (SUPERUSER CREATEDB LOGIN PASSWORD 'jarvis') and target database exist."""
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'jarvis';")
        if cur.fetchone() is None:
            cur.execute("CREATE ROLE jarvis WITH SUPERUSER CREATEDB LOGIN PASSWORD 'jarvis';")
            print("[setup_postgres] Created PostgreSQL role 'jarvis' (SUPERUSER CREATEDB LOGIN).")
        else:
            cur.execute("ALTER ROLE jarvis WITH SUPERUSER CREATEDB LOGIN PASSWORD 'jarvis';")

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER jarvis").format(sql.Identifier(target_db)))
            print(f"[setup_postgres] Created native PostgreSQL database '{target_db}'.")
        else:
            print(f"[setup_postgres] Native PostgreSQL database '{target_db}' already exists.")


def ensure_postgres_database(database_url: str | None = None) -> dict:
    """
    Connect to the native PostgreSQL maintenance database ('postgres' or admin URL),
    ensure the `jarvis` login role and target database ('jarvis') exist, and initialize
    all 8 Jarvis tables via ReminderStore.
    """
    resolved_url = resolve_database_url(database_url)
    maint_url, target_db = build_maintenance_url(resolved_url)

    if psycopg2 is None:
        msg = (
            "psycopg2 is not installed. Run: py -3.11 -m pip install psycopg2-binary\n"
            "Falling back to local SQL adapter via ReminderStore."
        )
        print(f"[setup_postgres] WARNING: {msg}")
        store = ReminderStore(database_url=resolved_url)
        return {
            "ok": False,
            "backend": store.backend,
            "database": target_db,
            "tables": list(REQUIRED_TABLES),
            "message": msg,
        }

    candidate_urls = [maint_url]
    if database_url is None:
        admin_env = os.environ.get("POSTGRES_ADMIN_URL")
        if admin_env and admin_env not in candidate_urls:
            candidate_urls.append(admin_env)
        for fb in FALLBACK_ADMIN_URLS:
            if fb not in candidate_urls:
                candidate_urls.append(fb)

    connected = False
    last_exc: Exception | None = None
    for url_try in candidate_urls:
        try:
            conn = psycopg2.connect(url_try, connect_timeout=3)
            _ensure_jarvis_role_and_db(conn, target_db)
            conn.close()
            connected = True
            break
        except Exception as exc:
            last_exc = exc

    if not connected:
        guidance = (
            f"[setup_postgres] Could not connect to native PostgreSQL at {maint_url}\n"
            f"  Reason: {last_exc}\n"
            "  Instructions:\n"
            "  1. Ensure PostgreSQL (pgAdmin) service is running on port 5432.\n"
            "  2. Verify credentials in backend/.env (`DATABASE_URL=postgresql://jarvis:jarvis@localhost:5432/jarvis`).\n"
            "  3. Initializing local SQL fallback tables so Jarvis remains immediately usable."
        )
        print(guidance)
        store = ReminderStore(database_url=resolved_url)
        return {
            "ok": False,
            "backend": store.backend,
            "database": target_db,
            "tables": list(REQUIRED_TABLES),
            "error": str(last_exc),
        }

    # Initialize all tables on the target database via ReminderStore
    store = ReminderStore(database_url=resolved_url)
    if store.backend == "postgres":
        with store._get_pg_connection() as target_conn:
            with target_conn.cursor() as cur:
                for stmt in POSTGRES_DDL_STATEMENTS:
                    cur.execute(stmt)
            target_conn.commit()

    print(
        f"[setup_postgres] Initialized Jarvis schema ({', '.join(REQUIRED_TABLES)}) "
        f"using backend='{store.backend}'."
    )
    return {
        "ok": store.backend == "postgres",
        "backend": store.backend,
        "database": target_db,
        "tables": list(REQUIRED_TABLES),
    }


def main() -> int:
    result = ensure_postgres_database()
    return 0 if result.get("backend") in ("postgres", "sqlite_compat") else 1


if __name__ == "__main__":
    sys.exit(main())
