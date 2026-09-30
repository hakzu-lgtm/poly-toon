"""프로젝트 저장 / 불러오기 — 세션 데이터를 폴더 단위로 관리"""

import json
import shutil
from datetime import datetime
from pathlib import Path

OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name)[:30].strip()


def save_project(
    name: str,
    settings: dict,
    story: dict,
    character_sheets: list[dict],
    cover_result: dict,
    panel_results: list[dict],
    layout_result: dict,
    bubble_result: dict,
) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize(name) or "project"
    folder_name = f"{safe_name}_{ts}"
    project_dir = OUTPUTS_DIR / folder_name
    project_dir.mkdir(parents=True, exist_ok=True)

    current_dir = OUTPUTS_DIR / "current"
    if current_dir.exists():
        for item in current_dir.iterdir():
            dst = project_dir / item.name
            if item.is_dir():
                shutil.copytree(str(item), str(dst), dirs_exist_ok=True)
            else:
                shutil.copy2(str(item), str(dst))

    def _strip_bytes(sheets):
        cleaned = []
        for s in sheets:
            c = dict(s)
            for v in c.get("views", []):
                v.pop("b64_preview", None)
            c.pop("b64_preview", None)
            cleaned.append(c)
        return cleaned

    def _strip_panel_bytes(panels):
        cleaned = []
        for p in panels:
            c = dict(p)
            for v in c.get("variants", []):
                v.pop("b64_preview", None)
            cleaned.append(c)
        return cleaned

    meta = {
        "name": name,
        "created": ts,
        "settings": settings,
        "story": story,
        "character_sheets": _strip_bytes(character_sheets),
        "cover_path": cover_result.get("path", "") if cover_result else "",
        "panel_results": _strip_panel_bytes(panel_results),
        "layout_path": layout_result.get("path", "") if layout_result else "",
        "bubble_path": bubble_result.get("path", "") if bubble_result else "",
    }

    (project_dir / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"folder": folder_name, "path": str(project_dir)}


def list_projects() -> list[dict]:
    projects = []
    for d in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if d.is_dir() and d.name != "current" and d.name != "style_previews":
            meta_path = d / "project.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    projects.append({
                        "folder": d.name,
                        "name": meta.get("name", d.name),
                        "created": meta.get("created", ""),
                        "title": meta.get("story", {}).get("title", ""),
                    })
                except Exception:
                    pass
    return projects


def load_project(folder: str) -> dict:
    project_dir = OUTPUTS_DIR / folder
    meta_path = project_dir / "project.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"프로젝트를 찾을 수 없습니다: {folder}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    current_dir = OUTPUTS_DIR / "current"
    if current_dir.exists():
        shutil.rmtree(str(current_dir))
    shutil.copytree(str(project_dir), str(current_dir), dirs_exist_ok=True)

    return meta
