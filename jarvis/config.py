"""Configuration loader, .env resolver, database URL resolver, and Groq/hardware profile manager for Jarvis."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


DEFAULT_POSTGRES_URL = os.environ.get("DATABASE_URL", "")
ADMIN_POSTGRES_URL = os.environ.get("POSTGRES_ADMIN_URL", "")
DEFAULT_GROQ_XLSX_PATH = os.environ.get("GROQ_KEYS_XLSX_PATH", "")


def load_dotenv_files(base_dir: Optional[Path] = None) -> Dict[str, str]:
    """Load key=value pairs from .env and backend/.env into os.environ (without clobbering existing env vars)."""
    root = base_dir or Path(__file__).resolve().parent.parent
    loaded: Dict[str, str] = {}
    for env_candidate in (root / "backend" / ".env", root / ".env"):
        if env_candidate.exists():
            try:
                for raw_line in env_candidate.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key:
                        loaded[key] = val
                        os.environ.setdefault(key, val)
            except Exception:
                pass
    return loaded


# Ensure .env / backend/.env variables are available on import
load_dotenv_files()


class STTConfig(BaseModel):
    model: str = "whisper-large-v3-turbo"
    compute_type: str = "int8"
    cuda_device: int = 1


class LLMConfig(BaseModel):
    model: str = "llama-3.3-70b-versatile"
    cuda_device: int = 0


class ProfileConfig(BaseModel):
    stt: STTConfig = Field(default_factory=STTConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)


class CalDAVConfig(BaseModel):
    url: str = "http://localhost:5232"
    user: str = "jarvis"
    password: str = "change-me"


class NtfyConfig(BaseModel):
    url: str = "http://localhost:8080"
    topic: str = "jarvis-reminders"


class TTSConfig(BaseModel):
    engine: str = "piper"
    language: str = "en"
    voice: Optional[str] = None


class GroqConfig(BaseModel):
    keys_xlsx_path: str = DEFAULT_GROQ_XLSX_PATH
    api_keys: List[str] = Field(default_factory=list)
    llm_model: str = "llama-3.3-70b-versatile"
    stt_model: str = "whisper-large-v3-turbo"
    cooldown_seconds: int = 60
    api_base_url: str = "https://api.groq.com/openai/v1"


class JarvisConfig(BaseModel):
    profile: str = "cloud_groq"
    timezone: str = "Asia/Karachi"
    inbox_dir: str = "./inbox"
    db_path: str = "./data/jarvis.db"
    database_url: str = Field(
        default_factory=lambda: os.environ.get("DATABASE_URL", DEFAULT_POSTGRES_URL)
    )
    groq_keys_xlsx_path: str = Field(
        default_factory=lambda: os.environ.get("GROQ_KEYS_XLSX_PATH", DEFAULT_GROQ_XLSX_PATH)
    )
    groq_api_keys: List[str] = Field(default_factory=list)
    groq: GroqConfig = Field(default_factory=GroqConfig)
    profiles: Dict[str, ProfileConfig] = Field(default_factory=dict)
    ollama_url: str = "http://localhost:11434"
    caldav: CalDAVConfig = Field(default_factory=CalDAVConfig)
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)

    def get_active_profile(self) -> ProfileConfig:
        if self.profile in self.profiles:
            return self.profiles[self.profile]
        return ProfileConfig()

    def get_abs_inbox_dir(self, base_dir: Optional[Path] = None) -> Path:
        base = base_dir or Path(__file__).resolve().parent.parent
        p = Path(self.inbox_dir)
        return p if p.is_absolute() else (base / p).resolve()

    def get_abs_db_path(self, base_dir: Optional[Path] = None) -> Path:
        base = base_dir or Path(__file__).resolve().parent.parent
        p = Path(self.db_path)
        return p if p.is_absolute() else (base / p).resolve()

    def get_database_url(self) -> str:
        return os.environ.get("DATABASE_URL") or self.database_url or DEFAULT_POSTGRES_URL


def load_config(config_path: Optional[str] = None) -> JarvisConfig:
    """Load configuration from YAML file with .env and environment overrides and fallback defaults."""
    load_dotenv_files()
    if not config_path:
        root = Path(__file__).resolve().parent.parent
        candidate = root / "config.yaml"
        if candidate.exists():
            config_path = str(candidate)

    data: Dict[str, Any] = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    if os.environ.get("DATABASE_URL"):
        data["database_url"] = os.environ["DATABASE_URL"]
    if os.environ.get("GROQ_KEYS_XLSX_PATH"):
        data["groq_keys_xlsx_path"] = os.environ["GROQ_KEYS_XLSX_PATH"]
    if os.environ.get("GROQ_API_KEYS"):
        env_keys = [k.strip() for k in os.environ["GROQ_API_KEYS"].split(",") if k.strip()]
        if env_keys:
            data["groq_api_keys"] = env_keys

    return JarvisConfig(**data)
