"""Main CLI entrypoint for Jarvis offline personal assistant."""

import argparse
import sys
from pathlib import Path
import uvicorn

from jarvis.briefing import DailyBriefing
from jarvis.config import load_config
from jarvis.extract import TaskExtractor
from jarvis.store import TaskStore
from jarvis.stt import SpeechToText
from jarvis.timeparse import parse_relative_time
from jarvis.watcher import InboxWatcher


DEFAULT_FIXED_ROUTINE = [
    # Monday - Wednesday: University (07:00-16:00 incl. 45m commute for 08:30 start) + Office (16:00-19:00) + Commute Home (19:00-20:00)
    ("Monday", "University Commute & Classes", "07:00", "16:00", "university"),
    ("Monday", "Office Work (Post-University)", "16:00", "19:00", "office"),
    ("Monday", "Commute Home & Dinner", "19:00", "20:00", "commute"),

    ("Tuesday", "University Commute & Classes", "07:00", "16:00", "university"),
    ("Tuesday", "Office Work (Post-University)", "16:00", "19:00", "office"),
    ("Tuesday", "Commute Home & Dinner", "19:00", "20:00", "commute"),

    ("Wednesday", "University Commute & Classes", "07:00", "16:00", "university"),
    ("Wednesday", "Office Work (Post-University)", "16:00", "19:00", "office"),
    ("Wednesday", "Commute Home & Dinner", "19:00", "20:00", "commute"),

    # Thursday & Friday: Full Day Office
    ("Thursday", "Office (Full Day)", "09:00", "18:00", "office"),
    ("Friday", "Office (Full Day)", "09:00", "18:00", "office"),

    # Saturday & Sunday: Full Day Work From Home
    ("Saturday", "Work From Home (Full Day)", "10:00", "18:00", "work"),
    ("Sunday", "Work From Home (Full Day)", "10:00", "18:00", "work"),
]


def seed_fixed_routine(store: TaskStore | None = None) -> int:
    """Idempotently seed or update the user's fixed weekly routine in the database."""
    db = store or TaskStore()
    existing = db.list_weekly_routine()
    by_key = {
        (str(b.get("day_of_week", "")).strip().lower(), str(b.get("title", "")).strip().lower()): b
        for b in existing
    }

    changed = 0
    for day, title, start_time, end_time, category in DEFAULT_FIXED_ROUTINE:
        key = (day.lower(), title.lower())
        match = by_key.get(key)
        if match:
            if (
                match.get("start_time") != start_time
                or match.get("end_time") != end_time
                or match.get("category") != category
            ):
                db.update_routine_block(
                    match["id"],
                    day_of_week=day,
                    title=title,
                    start_time=start_time,
                    end_time=end_time,
                    category=category,
                    is_locked=True,
                )
                changed += 1
        else:
            db.add_routine_block(
                day_of_week=day,
                title=title,
                start_time=start_time,
                end_time=end_time,
                category=category,
                is_locked=True,
            )
            changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(description="JARVIS: Offline Personal Voice Assistant")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the background watcher and web control center")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")

    # Command: briefing
    subparsers.add_parser("briefing", help="Trigger daily morning briefing")

    # Command: process
    proc_parser = subparsers.add_parser("process", help="Process an audio voice memo file directly")
    proc_parser.add_argument("file", help="Path to audio file (.m4a, .mp3, .wav, .ogg)")

    # Command: status
    subparsers.add_parser("status", help="Show system status and hardware profiles")

    # Command: test-parse
    test_parser = subparsers.add_parser("test-parse", help="Test Urdu-English time parser on a phrase")
    test_parser.add_argument("phrase", help="Phrase to parse, e.g. 'kal subah 9 baje'")

    # Command: seed
    subparsers.add_parser("seed", help="Seed or update fixed weekly routine in the database")

    args = parser.parse_args()

    if args.command == "run":
        cfg = load_config()
        seeded_count = seed_fixed_routine()
        print(f"[*] Starting Jarvis on {args.host}:{args.port}")
        print(f"[*] Active Profile: {cfg.profile}")
        print(f"[*] Timezone: {cfg.timezone}")
        print(f"[*] Fixed Routine Seeded/Updated: {seeded_count} change(s)")
        print(f"[*] Watching Inbox: {cfg.get_abs_inbox_dir()}")

        # Start background watcher
        watcher = InboxWatcher()
        watcher.start()

        # Run web dashboard
        try:
            uvicorn.run("jarvis.web:app", host=args.host, port=args.port, log_level="info")
        finally:
            watcher.stop()

    elif args.command == "briefing":
        engine = DailyBriefing()
        result = engine.generate_briefing()
        print(f"\n[Briefing Generated]:\n{result['text']}\n")
        if result.get("audio_path"):
            print(f"[Audio Synthesized]: {result['audio_path']}")

    elif args.command == "process":
        audio_path = Path(args.file).resolve()
        if not audio_path.exists():
            print(f"[-] Error: File not found: {args.file}")
            sys.exit(1)

        stt = SpeechToText()
        extractor = TaskExtractor()
        store = TaskStore()

        print(f"[*] Transcribing {audio_path.name}...")
        stt_res = stt.transcribe(str(audio_path))
        transcript = stt_res.get("text", "")
        print(f"[Transcript]: \"{transcript}\"")

        tasks = extractor.extract_tasks(transcript)
        print(f"[*] Extracted {len(tasks)} task(s):")
        for t in tasks:
            t_id = store.add_task(
                title=t["title"],
                description=t.get("description", ""),
                original_transcript=transcript,
                raw_due_text=t.get("raw_due_text", ""),
                due_datetime=t.get("due_datetime"),
                priority=t.get("priority", "normal"),
                status="pending_review"
            )
            print(f"  - [ID {t_id}] {t['title']} (Due: {t.get('due_datetime')}) [Status: pending_review]")

    elif args.command == "status":
        cfg = load_config()
        store = TaskStore()
        pending = store.get_pending_tasks()
        today = store.get_today_tasks()

        print("=== JARVIS SYSTEM STATUS ===")
        print(f"Profile:       {cfg.profile}")
        print(f"Timezone:      {cfg.timezone}")
        print(f"Database:      {cfg.get_abs_db_path()}")
        print(f"Inbox:         {cfg.get_abs_inbox_dir()}")
        print(f"Pending Memos: {len(pending)}")
        print(f"Today's Tasks: {len(today)}")

    elif args.command == "test-parse":
        dt = parse_relative_time(args.phrase)
        print(f"\nInput:  \"{args.phrase}\"")
        print(f"Parsed: {dt} (Timezone: {dt.tzinfo if dt else 'None'})\n")

    elif args.command == "seed":
        changed = seed_fixed_routine()
        print(f"[+] Fixed weekly routine seeded/updated ({changed} change(s)).")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

