"""Stage 5: 세로 스크롤 웹툰 페이지 배치"""

import base64
from pathlib import Path
from PIL import Image, ImageDraw

from backend.pipeline import panels


def layout_pages(
    panel_results: list[dict],
    story: dict,
    canvas_width: int = 800,
    panel_gap: int = 20,
    chapter_gap: int = 60,
    bg_color: str = "#FFFFFF",
    project_dir: Path = None,
) -> list[dict]:
    """선택된 컷 이미지를 세로로 배치하여 페이지 이미지 생성."""
    if project_dir is None:
        raise ValueError("project_dir required")

    output_dir = project_dir / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)

    chapters = story.get("chapters", [])
    if not chapters:
        chapters = [{"chapter_number": 1, "chapter_title": "", "panels": story.get("panels", [])}]

    panel_map = {}
    layout_keys = {}
    for pr in panel_results:
        sel = pr.get("selected", 0)
        variants = pr.get("variants", [])
        if variants:
            chosen = variants[min(sel, len(variants) - 1)]
            img_path = Path(chosen["path"])
            if img_path.exists():
                panel_map[pr["panel_number"]] = img_path
                if chosen.get("layout"):
                    layout_keys[pr["panel_number"]] = chosen["layout"]

    pages = []
    panel_positions = []

    panel_images = []
    layout_info = []

    for ci, ch in enumerate(chapters):
        if ci > 0:
            layout_info.append({"type": "chapter_gap", "height": chapter_gap})

        ch_num = ch.get("chapter_number", ci + 1)
        ch_title = ch.get("chapter_title", "")
        if len(chapters) > 1:
            layout_info.append({
                "type": "chapter_header",
                "chapter_number": ch_num,
                "chapter_title": ch_title,
                "height": 50,
            })

        for panel in ch.get("panels", []):
            pn = panel.get("panel_number", 0)
            if pn in panel_map:
                img = Image.open(panel_map[pn]).convert("RGB")
                ratio = canvas_width / img.width
                new_h = int(img.height * ratio)
                img = img.resize((canvas_width, new_h), Image.LANCZOS)
                panel_images.append((pn, img))
                story_layout = panel.get("layout", "")
                layout_info.append({
                    "layout": layout_keys.get(pn) or panels.LAYOUT_ALIASES.get(story_layout, story_layout),
                    "type": "panel",
                    "panel_number": pn,
                    "height": new_h,
                    "img_index": len(panel_images) - 1,
                })
            layout_info.append({"type": "gap", "height": panel_gap})

    total_h = sum(item["height"] for item in layout_info) + 40
    page = Image.new("RGB", (canvas_width, total_h), bg_color)
    draw = ImageDraw.Draw(page)

    y = 20
    for item in layout_info:
        if item["type"] == "panel":
            idx = item["img_index"]
            pn, img = panel_images[idx]
            page.paste(img, (0, y))
            panel_positions.append({
                "panel_number": pn,
                "layout": item.get("layout", ""),
                "x": 0, "y": y,
                "width": canvas_width,
                "height": item["height"],
            })
            y += item["height"]
        elif item["type"] == "chapter_header":
            draw.rectangle([0, y, canvas_width, y + item["height"]], fill="#F0F4FF")
            from backend.pipeline.bubbles import _load_font
            font = _load_font(20, bold=True)
            text = f"{item['chapter_number']}장  {item['chapter_title']}"
            draw.text((canvas_width // 2, y + 25), text, fill="#2563EB", font=font, anchor="mm")
            y += item["height"]
        elif item["type"] in ("gap", "chapter_gap"):
            y += item["height"]

    page_path = output_dir / "full_page.png"
    page.save(page_path, "PNG")

    b64 = base64.b64encode(page_path.read_bytes()).decode()

    return {
        "path": str(page_path),
        "b64_preview": b64,
        "width": canvas_width,
        "height": total_h,
        "panel_positions": panel_positions,
    }
