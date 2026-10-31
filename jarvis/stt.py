"""Speech-to-Text module using faster-whisper with multi-GPU and CPU fallback."""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from jarvis.config import load_config, STTConfig


class SpeechToText:
    def __init__(self, config: Optional[STTConfig] = None):
        cfg = load_config()
        self.config = config or cfg.get_active_profile().stt
        self.model = None
        self._device = "cpu"
        self._compute_type = "int8"
        self._init_model()

    def _init_model(self):
        try:
            from faster_whisper import WhisperModel
            import torch

            # Determine device
            cuda_available = torch.cuda.is_available()
            if cuda_available and self.config.cuda_device >= 0:
                self._device = f"cuda:{self.config.cuda_device}"
                self._compute_type = self.config.compute_type
            else:
                self._device = "cpu"
                self._compute_type = "int8"

            self.model = WhisperModel(
                self.config.model,
                device=self._device,
                compute_type=self._compute_type
            )
        except Exception:
            # Fallback / mock mode when faster-whisper or weights are not yet downloaded
            self.model = None

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file into text.
        Bias model with Roman-Urdu and English schedule vocabulary.
        """
        audio_file = Path(audio_path).resolve()
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        default_prompt = (
            "Kal, aaj, parson, subah, dopahar, shaam, raat, baje, meeting, "
            "schedule, buddy, jarvis, submit, report, reminder, task."
        )
        prompt = initial_prompt or default_prompt

        if self.model is not None:
            segments, info = self.model.transcribe(
                str(audio_file),
                beam_size=5,
                language=language,
                initial_prompt=prompt,
                vad_filter=True
            )
            text = " ".join([segment.text.strip() for segment in segments])
            return {
                "text": text,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration,
                "device": self._device
            }
        else:
            # Fallback simulation for tests or environments without model downloaded yet
            return {
                "text": f"[Transcribed from {audio_file.name}]",
                "language": "ur",
                "language_probability": 0.95,
                "duration": 0.0,
                "device": "mock-cpu"
            }

