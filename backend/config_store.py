import json
import os
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "host": "https://factchat-cloud.mindlogic.ai",
    "api_key": "",
    "models": {
        "story": "claude-opus-5-5",
        "panel_prompt": "claude-sonnet-5-5",
        "suggestions": "gemini-3.5-flash-lite",
        "image": "gpt-image-2.5-sunburst",
    },
    "image_quality": "medium",
    "max_frames_per_panel": 2,
    "use_reference_images": False,
    "font_path": r"C:\Windows\Fonts\malgun.ttf",
}


def load() -> dict:
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        merged = {**DEFAULT_CONFIG, **data}
        merged["models"] = {**DEFAULT_CONFIG["models"], **data.get("models", {})}
    else:
        merged = dict(DEFAULT_CONFIG)
    # 서버 배포 시 키는 환경변수로 받는다 (config/ 는 git에 올리지 않음)
    if os.environ.get("FACTCHAT_API_KEY") and not merged.get("api_key"):
        merged["api_key"] = os.environ["FACTCHAT_API_KEY"]
    return merged


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "****"
    return key[:4] + "*" * (len(key) - 4)
