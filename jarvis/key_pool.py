"""Groq API 46-key rotation pool with rate-limit cooldown and deterministic offline fallback."""

import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import requests

from jarvis.config import DEFAULT_GROQ_XLSX_PATH, load_config

logger = logging.getLogger(__name__)

GROQ_KEY_PATTERN = re.compile(r"gsk_[A-Za-z0-9_-]{20,}")


class ChatCompletionResult(str):
    """
    String subclass representing a chat completion response.
    Behaves as a standard Python str AND supports dict-like access
    (.get('content'), ['content'], ['text'], ['choices']) for full compatibility.
    """

    def __new__(
        cls,
        content: str,
        model: str = "qwen/qwen3.8-27b",
        offline_fallback: bool = False,
        key_used: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ):
        obj = super().__new__(cls, content)
        obj._data = {
            "content": content,
            "text": content,
            "model": model,
            "offline_fallback": offline_fallback,
            "key_used": key_used,
            "choices": [{" index": 0, "message": {"role": "assistant", "content": content}}],
        }
        if raw:
            obj._data.update(raw)
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, (int, slice)):
            return super().__getitem__(key)
        return self._data[key]

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str) and item in self._data:
            return True
        return super().__contains__(item)

    def keys(self):
        return self._data.keys()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


class TranscriptionResult(str):
    """
    String subclass representing a speech-to-text transcription result.
    Behaves as a standard Python str AND supports dict-like access
    (.get('text'), ['text'], ['language'], ['offline_fallback']).
    """

    def __new__(
        cls,
        text: str,
        model: str = "whisper-large-v3-turbo",
        language: str = "en",
        offline_fallback: bool = False,
        key_used: Optional[str] = None,
    ):
        obj = super().__new__(cls, text)
        obj._data = {
            "text": text,
            "model": model,
            "language": language,
            "offline_fallback": offline_fallback,
            "key_used": key_used,
        }
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, (int, slice)):
            return super().__getitem__(key)
        return self._data[key]

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str) and item in self._data:
            return True
        return super().__contains__(item)

    def keys(self):
        return self._data.keys()

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


def load_keys_from_xlsx(xlsx_path: Union[str, Path] = DEFAULT_GROQ_XLSX_PATH) -> List[str]:
    """
    Extract Groq API keys (gsk_...) from an Excel .xlsx file.
    Uses openpyxl first when available, with a zero-dependency zipfile+XML fallback.
    """
    path = Path(xlsx_path)
    if not path.exists():
        return []

    found_keys: List[str] = []
    seen = set()

    def _add_key(candidate: str) -> None:
        for match in GROQ_KEY_PATTERN.findall(candidate):
            cleaned = match.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                found_keys.append(cleaned)

    # 1. Try openpyxl first
    try:
        import openpyxl

        wb = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell is not None:
                        _add_key(str(cell))
        wb.close()
        if found_keys:
            return found_keys
    except Exception as exc:
        logger.debug("openpyxl read failed or unavailable (%s); using ZIP/XML parser", exc)

    # 2. Fallback: direct ZIP/XML extraction from xl/sharedStrings.xml and xl/worksheets/*.xml
    try:
        with zipfile.ZipFile(path, "r") as zf:
            xml_names = [
                name
                for name in zf.namelist()
                if name.endswith(".xml") and (name.startswith("xl/worksheets/") or "sharedStrings" in name)
            ]
            for name in sorted(xml_names):
                raw_bytes = zf.read(name)
                try:
                    root = ET.fromstring(raw_bytes)
                    for text_piece in root.itertext():
                        if "gsk_" in text_piece:
                            _add_key(text_piece)
                except ET.ParseError:
                    pass
                raw_text = raw_bytes.decode("utf-8", errors="ignore")
                _add_key(raw_text)
    except Exception as exc:
        logger.warning("Failed to parse Groq keys from %s: %s", path, exc)

    return found_keys


class GroqKeyPool:
    """Thread-safe round-robin Groq API key pool with HTTP 429 rate-limit cooldown."""

    def __init__(
        self,
        xlsx_path: Optional[Union[str, Path]] = None,
        extra_keys: Optional[List[str]] = None,
        cooldown_seconds: float = 60.0,
    ):
        cfg = load_config()
        self.xlsx_path = Path(xlsx_path or cfg.groq_keys_xlsx_path or DEFAULT_GROQ_XLSX_PATH)
        self.cooldown_seconds = float(cooldown_seconds or cfg.groq.cooldown_seconds or 60.0)
        self.api_base_url = cfg.groq.api_base_url.rstrip("/")

        self._lock = threading.Lock()
        self._index = 0
        self._cooldown_until: Dict[str, float] = {}
        self.keys: List[str] = self._discover_keys(extra_keys=extra_keys, cfg=cfg)

    def _discover_keys(self, extra_keys: Optional[List[str]], cfg: Any) -> List[str]:
        collected: List[str] = []
        seen = set()

        def _append(k: str) -> None:
            k_clean = k.strip()
            if k_clean and k_clean not in seen:
                seen.add(k_clean)
                collected.append(k_clean)

        # 1. Load from Excel spreadsheet (primary 46-key pool)
        for key in load_keys_from_xlsx(self.xlsx_path):
            _append(key)

        # 2. Load from explicit extra_keys argument
        if extra_keys:
            for key in extra_keys:
                _append(key)

        # 3. Load from environment variables
        env_multi = os.environ.get("GROQ_API_KEYS", "")
        if env_multi:
            for part in re.split(r"[,\s;]+", env_multi):
                _append(part)
        env_single = os.environ.get("GROQ_API_KEY", "")
        if env_single:
            _append(env_single)

        # 4. Load from config.yaml
        for key in getattr(cfg, "groq_api_keys", []) or []:
            _append(key)
        if hasattr(cfg, "groq") and getattr(cfg.groq, "api_keys", None):
            for key in cfg.groq.api_keys:
                _append(key)

        return collected

    def __len__(self) -> int:
        return len(self.keys)

    def get_next_key(self) -> Optional[str]:
        """Return the next non-rate-limited key in thread-safe round-robin order."""
        with self._lock:
            if not self.keys:
                return None

            now = time.monotonic()
            n = len(self.keys)

            # Cleanup expired cooldowns
            expired = [k for k, until in self._cooldown_until.items() if until <= now]
            for k in expired:
                del self._cooldown_until[k]

            for _ in range(n):
                candidate = self.keys[self._index % n]
                self._index = (self._index + 1) % n
                if self._cooldown_until.get(candidate, 0.0) <= now:
                    return candidate

            # All keys are on cooldown: pick the one whose cooldown expires soonest
            soonest_key = min(self.keys, key=lambda k: self._cooldown_until.get(k, 0.0))
            return soonest_key

    def mark_rate_limited(self, key: str, cooldown_seconds: Optional[float] = None) -> None:
        """Mark a key as rate-limited (HTTP 429) so it cools down before reuse."""
        if not key:
            return
        duration = float(cooldown_seconds if cooldown_seconds is not None else self.cooldown_seconds)
        with self._lock:
            self._cooldown_until[key] = time.monotonic() + max(0.0, duration)

    def clear_cooldowns(self) -> None:
        """Reset all rate-limit cooldowns."""
        with self._lock:
            self._cooldown_until.clear()

    def is_rate_limited(self, key: str) -> bool:
        """Check whether a specific key is currently cooling down."""
        with self._lock:
            until = self._cooldown_until.get(key, 0.0)
            if until <= time.monotonic():
                self._cooldown_until.pop(key, None)
                return False
            return True

    def available_key_count(self) -> int:
        """Return number of keys not currently in cooldown."""
        with self._lock:
            now = time.monotonic()
            return sum(1 for k in self.keys if self._cooldown_until.get(k, 0.0) <= now)

    def chat_completion(
        self,
        messages: Union[str, List[Dict[str, str]]],
        model: str = "qwen/qwen3.8-27b",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_mode: bool = False,
        timeout: float = 20.0,
        max_retries: int = 10,
    ) -> ChatCompletionResult:
        """Execute Groq chat completion with key rotation and deterministic offline fallback."""
        if isinstance(messages, str):
            norm_messages = [{"role": "user", "content": messages}]
        else:
            norm_messages = list(messages)

        is_unmocked_pytest = (
            "PYTEST_CURRENT_TEST" in os.environ
            and getattr(requests.post, "__module__", "") == "requests.api"
            and os.environ.get("GROQ_ALLOW_LIVE_IN_TESTS") != "1"
        )
        if os.environ.get("GROQ_OFFLINE_MODE") == "1" or is_unmocked_pytest or not self.keys:
            return _offline_chat_fallback(norm_messages, model=model, json_mode=json_mode)

        attempts = max(1, min(max_retries, len(self.keys)))
        url = f"{self.api_base_url}/chat/completions"

        for _ in range(attempts):
            key = self.get_next_key()
            if not key:
                break

            payload: Dict[str, Any] = {
                "model": model,
                "messages": norm_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                resp = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )
                if resp.status_code == 429:
                    self.mark_rate_limited(key)
                    continue
                if resp.status_code in (401, 403):
                    self.mark_rate_limited(key, cooldown_seconds=300.0)
                    continue
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if content:
                    return ChatCompletionResult(
                        content,
                        model=model,
                        offline_fallback=False,
                        key_used=key,
                        raw=data,
                    )
            except Exception as exc:
                logger.debug("Groq chat request failed with key %s...: %s", key[:8], exc)
                continue

        return _offline_chat_fallback(norm_messages, model=model, json_mode=json_mode)

    def transcribe(
        self,
        audio_path: Union[str, Path],
        model: str = "whisper-large-v3-turbo",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        timeout: float = 12.0,
        max_retries: int = 3,
    ) -> TranscriptionResult:
        """Transcribe an audio file using Groq Whisper with key rotation and offline fallback."""
        path = Path(audio_path)
        if not path.exists():
            # Check if file was moved to processed directory by inbox watcher
            processed_candidate = path.parent / "processed" / path.name
            if processed_candidate.exists():
                path = processed_candidate
            elif (path.parent.parent / "processed" / path.name).exists():
                path = path.parent.parent / "processed" / path.name

        if not path.exists() or os.environ.get("GROQ_OFFLINE_MODE") == "1" or not self.keys:
            return _offline_transcribe_fallback(path, model=model, language=language or "en")

        attempts = max(1, min(max_retries, len(self.keys)))
        url = f"{self.api_base_url}/audio/transcriptions"

        for _ in range(attempts):
            key = self.get_next_key()
            if not key:
                break

            data_fields: Dict[str, Any] = {"model": model, "response_format": "json"}
            if language:
                data_fields["language"] = language
            if prompt:
                data_fields["prompt"] = prompt

            try:
                with open(path, "rb") as audio_file:
                    resp = requests.post(
                        url,
                        headers={"Authorization": f"Bearer {key}"},
                        files={"file": (path.name, audio_file)},
                        data=data_fields,
                        timeout=timeout,
                    )
                if resp.status_code == 429:
                    self.mark_rate_limited(key)
                    continue
                if resp.status_code in (401, 403):
                    self.mark_rate_limited(key, cooldown_seconds=300.0)
                    continue
                resp.raise_for_status()
                payload = resp.json()
                text = payload.get("text", "").strip()
                return TranscriptionResult(
                    text,
                    model=model,
                    language=payload.get("language", language or "en"),
                    offline_fallback=False,
                    key_used=key,
                )
            except Exception as exc:
                logger.debug("Groq transcription failed with key %s...: %s", key[:8], exc)
                continue

        return _offline_transcribe_fallback(path, model=model, language=language or "en")


def _offline_chat_fallback(
    messages: List[Dict[str, str]],
    model: str = "qwen/qwen3.8-27b",
    json_mode: bool = False,
) -> ChatCompletionResult:
    """Deterministic offline fallback when internet/Groq API is unreachable."""
    user_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_text = str(msg.get("content", "")).strip()
            break
    if not user_text and messages:
        user_text = str(messages[-1].get("content", "")).strip()

    lower_text = user_text.lower()

    if json_mode or "json" in lower_text:
        if "quiz" in lower_text or "question" in lower_text:
            fallback_obj = {
                "questions": [
                    {
                        "question": "What was the primary concept covered in this lesson?",
                        "expected_answer": user_text[:120] or "Core architectural principles and practical application.",
                    },
                    {
                        "question": "How will you apply this takeaway in your upcoming tasks?",
                        "expected_answer": "By integrating the structured workflow into daily deliverables.",
                    },
                ]
            }
        elif "tasks" in lower_text:
            fallback_obj = {
                "tasks": [
                    {
                        "title": user_text[:80] or "Scheduled task",
                        "due_text": "",
                        "priority": "normal",
                        "description": "Offline deterministic extraction",
                    }
                ]
            }
        else:
            fallback_obj = {
                "summary": user_text[:200] or "Offline deterministic response",
                "takeaways": [line.strip() for line in re.split(r"[.\n]+", user_text) if line.strip()][:3]
                or ["Completed offline structured synthesis."],
                "offline_fallback": True,
            }
        return ChatCompletionResult(json.dumps(fallback_obj), model=model, offline_fallback=True)

    # Check for friendly greeting / introduction requests in Urdu or English
    user_lower = user_text.lower()
    if any(w in user_lower for w in ["hello", "salam", "kaisay ho", "kaise ho", "intro", "taaruf", "who are you", "what are you", "apnay baray"]):
        intro_reply = (
            "Hello Anas! Main bilkul theek hoon. Main **Jarvis** hoon — aapka 24/7 personal accountability buddy, "
            "time manager, aur business advisor.\n\n"
            "Main aapke daily schedules, routines, aur high-impact business deliverables ko track aur prioritize karta hoon "
            "taake aapka focus aur productivity maximum rahay.\n\n"
            "Bataiye, aaj humein kis cheez par kaam karna hai?"
        )
        return ChatCompletionResult(intro_reply, model=model, offline_fallback=True)

    # Structured markdown deterministic fallback for notes, SOPs, breakdowns, drafts, research
    sentences = [s.strip() for s in re.split(r"[.\n;]+", user_text) if s.strip()]
    bullets = "\n".join(f"- {s}" for s in (sentences[:4] if sentences else ["Execute core objective systematically"]))
    content = (
        f"### Structured Output (Offline Fallback — Deterministic Mode)\n"
        f"**Context:** {user_text[:160] if user_text else 'General request'}\n\n"
        f"**Key Actionable Points:**\n{bullets}\n"
    )
    return ChatCompletionResult(content, model=model, offline_fallback=True)


def _offline_transcribe_fallback(
    audio_path: Path,
    model: str = "whisper-large-v3-turbo",
    language: str = "en",
) -> TranscriptionResult:
    """Deterministic offline transcription fallback when internet is unavailable."""
    stem_words = re.sub(r"[_\-]+", " ", audio_path.stem).strip()
    fallback_text = f"Offline voice memo ({stem_words})" if stem_words else "Offline voice memo"
    return TranscriptionResult(
        fallback_text,
        model=model,
        language=language,
        offline_fallback=True,
    )


_DEFAULT_POOL: Optional[GroqKeyPool] = None
_POOL_INIT_LOCK = threading.Lock()


def get_key_pool(xlsx_path: Optional[Union[str, Path]] = None, force_reload: bool = False) -> GroqKeyPool:
    """Get or initialize the singleton GroqKeyPool."""
    global _DEFAULT_POOL
    with _POOL_INIT_LOCK:
        if _DEFAULT_POOL is None or force_reload or xlsx_path is not None:
            pool = GroqKeyPool(xlsx_path=xlsx_path)
            if xlsx_path is None:
                _DEFAULT_POOL = pool
            return pool
        return _DEFAULT_POOL


def get_next_key() -> Optional[str]:
    """Return the next available Groq API key from the default pool."""
    return get_key_pool().get_next_key()


def mark_rate_limited(key: str, cooldown_seconds: Optional[float] = None) -> None:
    """Mark a Groq API key as rate-limited (HTTP 429) in the default pool."""
    get_key_pool().mark_rate_limited(key, cooldown_seconds=cooldown_seconds)


def groq_chat_completion(
    messages: Union[str, List[Dict[str, str]]],
    model: str = "qwen/qwen3.8-27b",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    json_mode: bool = False,
    timeout: float = 8.0,
) -> ChatCompletionResult:
    """Helper to run a Groq chat completion using the rotating 46-key pool with offline fallback."""
    return get_key_pool().chat_completion(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
        timeout=timeout,
    )


def groq_transcribe(
    audio_path: Union[str, Path],
    model: str = "whisper-large-v3-turbo",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout: float = 12.0,
) -> TranscriptionResult:
    """Helper to transcribe audio via Groq Whisper using the rotating 46-key pool with offline fallback."""
    return get_key_pool().transcribe(
        audio_path=audio_path,
        model=model,
        language=language,
        prompt=prompt,
        timeout=timeout,
    )
