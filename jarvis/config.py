"""Configuration loader and hardware profile manager for Jarvis."""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field


class STTConfig(BaseModel):
    model: str = "medium"
    compute_type: str = "int8"
    cuda_device: int = 1


class LLMConfig(BaseModel):
    model: str = "qwen2.5:7b-instruct-q4_K_M"
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


class JarvisConfig(BaseModel):
    profile: str = "dual_pascal"
    timezone: str = "Asia/Karachi"
    inbox_dir: str = "./inbox"
    db_path: str = "./data/jarvis.db"
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


def load_config(config_path: Optional[str] = None) -> JarvisConfig:
    """Load configuration from YAML file with fallback to defaults."""
    if not config_path:
        # Search relative to repo root
        root = Path(__file__).resolve().parent.parent
        candidate = root / "config.yaml"
        if candidate.exists():
            config_path = str(candidate)

    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return JarvisConfig(**data)

    return JarvisConfig()

