"""Inbox directory watcher with non-blocking queue worker for audio memos."""

import logging
import os
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Optional
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from jarvis.config import load_config
from jarvis.extract import TaskExtractor
from jarvis.store import TaskStore
from jarvis.stt import SpeechToText

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg", ".webm"}


class AudioInboxHandler(FileSystemEventHandler):
    def __init__(self, task_queue: queue.Queue):
        super().__init__()
        self.task_queue = task_queue

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS and "processed" not in path.parts:
            # Immediately enqueue without blocking the filesystem observer thread
            self.task_queue.put(path)


class InboxWatcher:
    def __init__(self, inbox_dir: Optional[str] = None):
        cfg = load_config()
        self.inbox_path = Path(inbox_dir) if inbox_dir else cfg.get_abs_inbox_dir()
        self.inbox_path.mkdir(parents=True, exist_ok=True)

        self.store = TaskStore()
        self.stt = SpeechToText()
        self.extractor = TaskExtractor()

        self.task_queue: queue.Queue = queue.Queue()
        self.observer = Observer()
        self.handler = AudioInboxHandler(self.task_queue)

        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._process_queue_worker, daemon=True)

    def start(self):
        self.observer.schedule(self.handler, str(self.inbox_path), recursive=False)
        self.observer.start()
        self._worker_thread.start()
        logger.info("Inbox watcher and async queue worker started on %s", self.inbox_path)

    def stop(self):
        self._stop_event.set()
        self.observer.stop()
        self.observer.join()

    def _process_queue_worker(self):
        """Dedicated background worker draining the incoming audio queue."""
        while not self._stop_event.is_set():
            try:
                audio_path: Path = self.task_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._wait_and_process(audio_path)
            except Exception as e:
                logger.error("Error processing queued audio %s: %s", audio_path, e)
            finally:
                self.task_queue.task_done()

    def _wait_and_process(self, path: Path):
        if not path.exists():
            return

        # Wait until file finishes writing/syncing (Syncthing completion)
        settled = False
        prev_size = -1
        for _ in range(12):
            if self._stop_event.is_set() or not path.exists():
                return
            try:
                size = path.stat().st_size
                if size > 0 and size == prev_size:
                    settled = True
                    break
                prev_size = size
            except Exception:
                pass
            time.sleep(0.5)

        if not settled:
            return

        self.process_audio(path)

    def process_audio(self, audio_path: Path):
        """Transcribe and extract tasks from audio file into SQLite pending queue."""
        try:
            logger.info("Processing voice memo: %s", audio_path.name)
            # 1. Transcribe audio
            stt_res = self.stt.transcribe(str(audio_path))
            transcript = stt_res.get("text", "").strip()

            if not transcript:
                logger.warning("Empty transcript for %s", audio_path.name)
                return

            # 2. Extract structured tasks and clarification recommendations
            extracted = self.extractor.extract_tasks(transcript)

            # 3. Add to TaskStore as pending_review
            created_ids = []
            for item in extracted:
                t_id = self.store.add_task(
                    title=item["title"],
                    description=item.get("description", ""),
                    original_transcript=transcript,
                    raw_due_text=item.get("raw_due_text", ""),
                    due_datetime=item.get("due_datetime"),
                    priority=item.get("priority", "normal"),
                    status="pending_review",
                    clarification_question=item.get("clarification_question"),
                    recommendation=item.get("recommendation")
                )
                created_ids.append(t_id)

            # 4. Move to processed subfolder
            processed_dir = audio_path.parent / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)
            target = processed_dir / audio_path.name
            if target.exists():
                target = processed_dir / f"{audio_path.stem}_{int(time.time())}{audio_path.suffix}"
            shutil.move(str(audio_path), str(target))

            logger.info("Successfully created %d pending tasks for %s", len(created_ids), audio_path.name)
        except Exception as e:
            logger.error("Failed to process audio %s: %s", audio_path, e)
