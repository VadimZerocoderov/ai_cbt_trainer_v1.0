# app/utils.py
import json, time
from pathlib import Path
from typing import Dict, Any

LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def log_event(user_id: int, case_id: str, step: int, client_text: str, user_reply: str, is_good: bool):
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "case_id": case_id,
        "step": step,
        "client": client_text,
        "reply": user_reply,
        "is_good": is_good
    }
    path = LOG_DIR / f"session_{user_id}_{case_id}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return str(path)
