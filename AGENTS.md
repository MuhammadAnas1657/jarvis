# Instructions for the coding agent

- Read PLAN.md first, then work through its phases in order. Tick the checkboxes as you go.
- Everything must run offline. Don't add cloud services or online translators.
- Don't add email, Home Assistant or smart-home features.
- This project is separate from `c:\projects\temp for atarion solutions budget`. Don't modify that project.
- Keep Whisper and Ollama in separate processes, pinned per GPU via `CUDA_VISIBLE_DEVICES`.
- Date and time computation must be deterministic code. The LLM only extracts structured data.
- Never write a task or run an action without user confirmation.
- Write tests for `timeparse.py` with Urdu and English examples.
- Target Windows with PowerShell and Python 3.11.
- Start with Phase 1. Ask the user before starting Phase 3.

