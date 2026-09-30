import json
import threading
from datetime import datetime
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
USAGE_FILE = CONFIG_DIR / "usage.json"
# 실패를 포함한 모든 이미지 요청 기록 (한 줄에 JSON 하나)
IMAGE_CALL_LOG = CONFIG_DIR / "image_calls.jsonl"

_lock = threading.Lock()


def _default() -> dict:
    now = datetime.now()
    return {
        "month": now.strftime("%Y-%m"),
        "text_calls": 0,
        "image_calls": 0,
        "image_edit_calls": 0,
        "image_requests": 0,
        "image_failed_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


def load() -> dict:
    now_month = datetime.now().strftime("%Y-%m")
    if USAGE_FILE.exists():
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        if data.get("month") != now_month:
            data = _default()
            save(data)
        return data
    return _default()


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_text(input_tokens: int = 0, output_tokens: int = 0) -> None:
    with _lock:
        d = load()
        d["text_calls"] += 1
        d["total_input_tokens"] += input_tokens
        d["total_output_tokens"] += output_tokens
        save(d)


def record_image() -> None:
    with _lock:
        d = load()
        d["image_calls"] += 1
        save(d)


def record_image_edit() -> None:
    with _lock:
        d = load()
        d["image_edit_calls"] += 1
        save(d)


def log_image_call(kind: str, model: str, status) -> None:
    """성공·실패와 관계없이 게이트웨이로 나간 이미지 요청을 모두 기록한다."""
    with _lock:
        d = load()
        d["image_requests"] = d.get("image_requests", 0) + 1
        if status != 200:
            d["image_failed_requests"] = d.get("image_failed_requests", 0) + 1
        save(d)
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "kind": kind, "model": model, "status": status,
        }
        with IMAGE_CALL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
