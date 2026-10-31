"""Task extraction from voice transcripts using local Ollama LLM and deterministic fallback."""

import json
import re
from typing import Any, Dict, List, Optional
import requests
from pydantic import BaseModel, Field

from jarvis.config import load_config
from jarvis.timeparse import parse_time_with_analysis


class ExtractedTask(BaseModel):
    title: str
    description: str = ""
    due_phrase: str = ""
    priority: str = "normal"
    clarification_question: Optional[str] = None
    recommendation: Optional[str] = None


class ExtractedBatch(BaseModel):
    tasks: List[ExtractedTask] = Field(default_factory=list)


SYSTEM_PROMPT = """You are JARVIS, an offline personal assistant specialized in extracting schedule items and tasks from spoken Roman-Urdu and English.
Analyze the user's spoken transcript. Extract all tasks and reminders.
For each task, return:
- title: concise action title in English or clean Roman-Urdu
- description: extra details or context
- due_phrase: exact time/day mentioned (e.g., 'kal subah 9 baje', 'parson shaam', 'tomorrow at 4pm')
- priority: 'low', 'normal', 'high', or 'urgent'
- clarification_question: if information is missing or ambiguous (e.g. 'No time specified. What time do you prefer?')
- recommendation: your suggested scheduling plan

Output ONLY valid JSON matching this schema:
{
  "tasks": [
    {
      "title": "Client meeting with Atarion",
      "description": "Discuss project budget",
      "due_phrase": "kal subah 9 baje",
      "priority": "high",
      "clarification_question": null,
      "recommendation": "Scheduled for tomorrow at 9:00 AM PKT"
    }
  ]
}
"""


class TaskExtractor:
    def __init__(self, ollama_url: Optional[str] = None, model: Optional[str] = None):
        cfg = load_config()
        self.ollama_url = ollama_url or cfg.ollama_url
        self.model = model or cfg.get_active_profile().llm.model

    def extract_tasks(self, transcript: str) -> List[Dict[str, Any]]:
        """
        Extract tasks from transcript using Ollama if running,
        or fallback to rule-based heuristic extraction.
        """
        if not transcript or not transcript.strip():
            return []

        # 1. Attempt LLM extraction via Ollama
        llm_batch = self._call_ollama(transcript)
        if llm_batch and llm_batch.tasks:
            tasks = []
            for t in llm_batch.tasks:
                due_dt, analysis = parse_time_with_analysis(t.due_phrase) if t.due_phrase else (None, {})
                clarification = t.clarification_question or analysis.get("clarification")
                recommendation = t.recommendation or analysis.get("recommendation")

                tasks.append({
                    "title": t.title,
                    "description": t.description,
                    "raw_due_text": t.due_phrase,
                    "due_datetime": due_dt,
                    "priority": t.priority,
                    "clarification_question": clarification,
                    "recommendation": recommendation,
                    "original_transcript": transcript
                })
            return tasks

        # 2. Offline heuristic fallback if Ollama is not active
        return self._heuristic_extract(transcript)

    def _call_ollama(self, transcript: str) -> Optional[ExtractedBatch]:
        try:
            payload = {
                "model": self.model,
                "prompt": f"{SYSTEM_PROMPT}\n\nSpoken Transcript:\n\"{transcript}\"\n\nJSON:",
                "stream": False,
                "format": "json"
            }
            resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=8)
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "{}")
                data = json.loads(raw_json)
                if isinstance(data, list):
                    data = {"tasks": data}
                return ExtractedBatch(**data)
        except Exception:
            pass
        return None

    def _heuristic_extract(self, transcript: str) -> List[Dict[str, Any]]:
        """Rule-based extractor when LLM service is offline."""
        cleaned = transcript.strip()
        # Remove conversational filler prefixes
        cleaned_title = re.sub(r'^(buddy|jarvis|hey jarvis|please|bhai|yaar|meherbani karke)\s*[,:]?\s*', '', cleaned, flags=re.I)
        cleaned_title = re.sub(r'\s*(schedule kar dena|schedule kardo|kar dena|kardo|yaad rakhna).*$', '', cleaned_title, flags=re.I)

        # Detect time phrases
        time_patterns = [
            r'(?:kal|aaj|parson|tarson)\s+(?:subah|dopahar|shaam|raat)?\s*(?:\d{1,2}(?::\d{2})?\s*baje)?',
            r'\d{1,2}(?::\d{2})?\s*(?:baje|am|pm)',
            r'(?:subah|dopahar|shaam|raat)\s+\d{1,2}\s*baje',
            r'(?:tomorrow|today|tonight|next week)\s*(?:at\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?',
            r'aadhe ghantay baad|\d+\s*(?:minute|ghanta)\s*baad'
        ]

        due_phrase = ""
        for pattern in time_patterns:
            match = re.search(pattern, cleaned, flags=re.I)
            if match:
                due_phrase = match.group(0).strip()
                break

        due_dt, analysis = parse_time_with_analysis(due_phrase) if due_phrase else (None, {})

        if due_phrase:
            title = re.sub(re.escape(due_phrase), '', cleaned_title, flags=re.I).strip()
            title = re.sub(r'\s{2,}', ' ', title).strip(" ,.-")
        else:
            title = cleaned_title

        if not title:
            title = "Scheduled voice memo"

        priority = "normal"
        if any(w in cleaned.lower() for w in ["urgent", "zaroori", "important", "asap"]):
            priority = "urgent"

        return [{
            "title": title.capitalize(),
            "description": f"Transcribed voice task: {cleaned}",
            "raw_due_text": due_phrase,
            "due_datetime": due_dt,
            "priority": priority,
            "clarification_question": analysis.get("clarification"),
            "recommendation": analysis.get("recommendation"),
            "original_transcript": transcript
        }]
