"""Stage 7: PNG / PDF / ZIP 내보내기"""

import json
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_individual_panels(
    panel_results: list[dict], project_dir: Path
) -> list[str]:
    """선택된 컷을 개별 PNG로 저장."""
    out = _ensure_dir(project_dir / "export" / "panels")
    paths = []
    for pr in panel_results:
        sel = pr.get("selected", 0)
        variants = pr.get("variants", [])
        if not variants:
            continue
        chosen = variants[min(sel, len(variants) - 1)]
        src = Path(chosen["path"])
        if src.exists():
            dst = out / f"panel_{pr['panel_number']:02d}.png"
            if src != dst:
                dst.write_bytes(src.read_bytes())
            paths.append(str(dst))
    return paths


def export_pdf(final_page_path: str, project_dir: Path) -> str:
    """완성 페이지를 PDF로 변환."""
    out = _ensure_dir(project_dir / "export")
    pdf_path = out / "webtoon.pdf"

    img = Image.open(final_page_path).convert("RGB")
    w, h = img.size

    max_page_h = 3000
    pages = []

    if h <= max_page_h:
        pages.append(img)
    else:
        y = 0
        while y < h:
            crop_h = min(max_page_h, h - y)
            page = img.crop((0, y, w, y + crop_h))
            pages.append(page)
            y += crop_h

    if pages:
        pages[0].save(
            str(pdf_path), "PDF", save_all=True,
            append_images=pages[1:] if len(pages) > 1 else [],
            resolution=150,
        )

    return str(pdf_path)


def export_zip(
    story: dict,
    panel_results: list[dict],
    character_sheets: list[dict],
    cover_result: dict,
    layout_result: dict,
    bubble_result: dict,
    project_dir: Path,
) -> str:
    """모든 결과물을 ZIP으로 묶기."""
    out = _ensure_dir(project_dir / "export")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = story.get("title", "webtoon").replace(" ", "_")[:20]
    zip_name = f"{title}_{timestamp}.zip"
    zip_path = out / zip_name

    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("scenario.json", json.dumps(story, ensure_ascii=False, indent=2))

        for cs in character_sheets:
            for view in cs.get("views", []):
                p = Path(view.get("path", ""))
                if p.exists():
                    zf.write(str(p), f"characters/{p.name}")

        if cover_result:
            p = Path(cover_result.get("path", ""))
            if p.exists():
                zf.write(str(p), f"cover/{p.name}")

        for pr in panel_results:
            sel = pr.get("selected", 0)
            variants = pr.get("variants", [])
            if variants:
                chosen = variants[min(sel, len(variants) - 1)]
                p = Path(chosen["path"])
                if p.exists():
                    zf.write(str(p), f"panels/panel_{pr['panel_number']:02d}.png")

        if layout_result:
            p = Path(layout_result.get("path", ""))
            if p.exists():
                zf.write(str(p), "pages/layout.png")

        if bubble_result:
            p = Path(bubble_result.get("path", ""))
            if p.exists():
                zf.write(str(p), "pages/final_with_bubbles.png")

        pdf_path = out / "webtoon.pdf"
        if pdf_path.exists():
            zf.write(str(pdf_path), "webtoon.pdf")

    return str(zip_path)
