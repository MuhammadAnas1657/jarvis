"""Backend entry point for running Jarvis FastAPI server via `uvicorn main:app --reload --port 8000`."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.config import load_dotenv_files  # noqa: E402

load_dotenv_files(PROJECT_ROOT)

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from jarvis.web import app  # noqa: E402

raw_origins = os.environ.get("CORS_ORIGINS", "*").strip()
allow_origins = ["*"] if raw_origins == "*" else [o.strip() for o in raw_origins.split(",") if o.strip()]

_has_cors = any(
    getattr(mw, "cls", None) is CORSMiddleware for mw in getattr(app, "user_middleware", [])
)
if not _has_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=True)
