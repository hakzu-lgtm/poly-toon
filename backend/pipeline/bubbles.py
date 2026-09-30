"""Stage 6: 말풍선 + 한글 대사 합성 (Pillow) — 감정별 말풍선 스타일"""

import base64
import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int, bold: bool = False, font_path: str = "") -> ImageFont.FreeTypeFont:
    candidates = []
    if font_path:
        candidates.append(font_path)
    if bold:
        candidates.append(r"C:\Windows\Fonts\malgunbd.ttf")
    candidates.append(r"C:\Windows\Fonts\malgun.ttf")
    candidates.append(r"C:\Windows\Fonts\gulim.ttc")
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = font.getbbox(test)
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _detect_mood(mood_str: str) -> str:
    """컷의 mood 문자열에서 말풍선 스타일을 결정."""
    m = (mood_str or "").lower()
    if any(k in m for k in ["angry", "rage", "fury", "분노", "화", "격분"]):
        return "angry"
    if any(k in m for k in ["whisper", "quiet", "secret", "속삭", "조용", "비밀"]):
        return "whisper"
    if any(k in m for k in ["think", "thought", "wonder", "생각", "고민", "상상"]):
        return "thought"
    if any(k in m for k in ["shout", "yell", "scream", "외침", "소리", "큰소리"]):
        return "shout"
    if any(k in m for k in ["sad", "cry", "sorrow", "슬", "울", "눈물"]):
        return "sad"
    return "normal"


# ── 말풍선 그리기 (스타일별) ──────────────────────────────────────

def _draw_bubble_normal(draw, bx, by, bw, bh, tail_dir):
    """일반 말풍선: 흰색 둥근 사각형 + 삼각형 꼬리"""
    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=14, fill="white", outline="#B0B8C4", width=2)
    tail_y = by + bh
    tail_x = bx + 20 if tail_dir == "left" else bx + bw - 30
    draw.polygon([(tail_x, tail_y - 2), (tail_x + 10, tail_y + 12),
                  (tail_x + 18, tail_y - 2)], fill="white", outline="#B0B8C4")
    draw.rectangle([tail_x + 1, tail_y - 3, tail_x + 17, tail_y + 1], fill="white")


def _draw_bubble_angry(draw, bx, by, bw, bh, tail_dir):
    """분노 말풍선: 빨간 테두리 뾰족한 사각형"""
    spike = 6
    pts = []
    for i in range(0, bw, 18):
        pts.append((bx + i, by))
        pts.append((bx + i + 9, by - spike))
    pts.append((bx + bw, by))
    for i in range(0, bh, 18):
        pts.append((bx + bw, by + i))
        pts.append((bx + bw + spike, by + i + 9))
    pts.append((bx + bw, by + bh))
    for i in range(bw, 0, -18):
        pts.append((bx + i, by + bh))
        pts.append((bx + i - 9, by + bh + spike))
    pts.append((bx, by + bh))
    for i in range(bh, 0, -18):
        pts.append((bx, by + i))
        pts.append((bx - spike, by + i - 9))
    draw.polygon(pts, fill="#FFF5F5", outline="#EF4444", width=2)


def _draw_bubble_whisper(draw, bx, by, bw, bh, tail_dir):
    """속삭임 말풍선: 점선 테두리"""
    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=14, fill="#FAFAFA", outline="#CBD5E1", width=1)
    dash_len = 6
    gap = 4
    for side_x in [bx, bx + bw]:
        y_pos = by
        while y_pos < by + bh:
            draw.line([(side_x, y_pos), (side_x, min(y_pos + dash_len, by + bh))],
                      fill="#94A3B8", width=1)
            y_pos += dash_len + gap


def _draw_bubble_thought(draw, bx, by, bw, bh, tail_dir):
    """생각 말풍선: 구름 형태 + 작은 원 꼬리"""
    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=20, fill="white", outline="#A5B4FC", width=2)
    bumps = int(bw / 24)
    for i in range(bumps):
        cx = bx + 12 + i * (bw - 24) // max(bumps - 1, 1)
        draw.ellipse([cx - 8, by - 6, cx + 8, by + 6], fill="white", outline="#A5B4FC", width=1)
        draw.ellipse([cx - 8, by + bh - 6, cx + 8, by + bh + 6], fill="white", outline="#A5B4FC", width=1)
    tail_x = bx + 20 if tail_dir == "left" else bx + bw - 30
    draw.ellipse([tail_x, by + bh + 4, tail_x + 12, by + bh + 14],
                 fill="white", outline="#A5B4FC", width=1)
    draw.ellipse([tail_x + 4, by + bh + 16, tail_x + 10, by + bh + 22],
                 fill="white", outline="#A5B4FC", width=1)


def _draw_bubble_shout(draw, bx, by, bw, bh, tail_dir):
    """외침 말풍선: 굵은 테두리 + 노란 배경"""
    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=10, fill="#FFFBEB", outline="#F59E0B", width=3)
    tail_y = by + bh
    tail_x = bx + 16 if tail_dir == "left" else bx + bw - 28
    draw.polygon([(tail_x, tail_y - 2), (tail_x + 8, tail_y + 14),
                  (tail_x + 20, tail_y - 2)], fill="#FFFBEB", outline="#F59E0B", width=2)
    draw.rectangle([tail_x + 2, tail_y - 4, tail_x + 18, tail_y + 1], fill="#FFFBEB")


def _draw_bubble_sad(draw, bx, by, bw, bh, tail_dir):
    """슬픔 말풍선: 파란 톤 둥근 사각형"""
    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=16, fill="#EFF6FF", outline="#93C5FD", width=2)
    tail_y = by + bh
    tail_x = bx + 20 if tail_dir == "left" else bx + bw - 30
    draw.polygon([(tail_x, tail_y - 2), (tail_x + 10, tail_y + 10),
                  (tail_x + 18, tail_y - 2)], fill="#EFF6FF", outline="#93C5FD")
    draw.rectangle([tail_x + 1, tail_y - 3, tail_x + 17, tail_y + 1], fill="#EFF6FF")


BUBBLE_STYLES = {
    "normal": _draw_bubble_normal,
    "angry": _draw_bubble_angry,
    "whisper": _draw_bubble_whisper,
    "thought": _draw_bubble_thought,
    "shout": _draw_bubble_shout,
    "sad": _draw_bubble_sad,
}

TEXT_COLORS = {
    "normal": "#1B2330",
    "angry": "#991B1B",
    "whisper": "#64748B",
    "thought": "#4338CA",
    "shout": "#92400E",
    "sad": "#1E40AF",
}


def _draw_speech_bubble(draw, x, y, text_lines, font, tail_direction="left",
                         max_bubble_w=300, mood="normal"):
    line_h = font.getbbox("가")[3] - font.getbbox("가")[1] + 6
    padding_x, padding_y = 16, 12

    widths = [font.getbbox(l)[2] - font.getbbox(l)[0] for l in text_lines]
    text_w = max(widths) if widths else 50
    text_h = line_h * len(text_lines)

    bubble_w = min(text_w + padding_x * 2, max_bubble_w)
    bubble_h = text_h + padding_y * 2

    style_fn = BUBBLE_STYLES.get(mood, BUBBLE_STYLES["normal"])
    style_fn(draw, x, y, bubble_w, bubble_h, tail_direction)

    text_color = TEXT_COLORS.get(mood, "#1B2330")
    ty = y + padding_y
    for line in text_lines:
        draw.text((x + padding_x, ty), line, fill=text_color, font=font)
        ty += line_h

    return bubble_w, bubble_h + 14


def _draw_narration_box(draw, x, y, text_lines, font, box_width=300):
    line_h = font.getbbox("가")[3] - font.getbbox("가")[1] + 6
    padding_x, padding_y = 14, 10
    text_h = line_h * len(text_lines)
    box_h = text_h + padding_y * 2

    draw.rectangle([x, y, x + box_width, y + box_h],
                   fill="#F8F9FA", outline="#94A3B8", width=1)
    ty = y + padding_y
    for line in text_lines:
        draw.text((x + padding_x, ty), line, fill="#475569", font=font)
        ty += line_h
    return box_width, box_h


def compose_bubbles(
    page_path: str,
    panel_positions: list[dict],
    story: dict,
    font_path: str = "",
    project_dir: Path = None,
) -> dict:
    """페이지 이미지에 감정별 말풍선/대사를 합성."""
    if project_dir is None:
        raise ValueError("project_dir required")

    output_dir = project_dir / "final"
    output_dir.mkdir(parents=True, exist_ok=True)

    page = Image.open(page_path).convert("RGB")
    draw = ImageDraw.Draw(page)

    font = _load_font(16, font_path=font_path)
    font_narr = _load_font(14, font_path=font_path)

    all_panels = []
    for ch in story.get("chapters", []):
        all_panels.extend(ch.get("panels", []))
    if not all_panels:
        all_panels = story.get("panels", [])

    panel_data = {p["panel_number"]: p for p in all_panels}
    characters = story.get("characters", [])
    char_names = {c["id"]: c["name"] for c in characters}

    for pos in panel_positions:
        pn = pos["panel_number"]
        panel = panel_data.get(pn)
        if not panel:
            continue

        dialogues = panel.get("dialogue", [])
        if not dialogues:
            continue

        px, py = pos["x"], pos["y"]
        pw, ph = pos["width"], pos["height"]
        mood = _detect_mood(panel.get("mood", ""))
        max_bubble_w = int(pw * 0.45)
        bubble_y = py + 10
        speech_idx = 0

        for dlg in dialogues:
            text = dlg.get("text", "")
            dtype = dlg.get("type", "speech")
            char_id = dlg.get("character")

            if not text:
                continue

            if dtype == "narration":
                lines = _wrap_text(text, font_narr, max_bubble_w - 28)
                narr_x = px + (pw - max_bubble_w) // 2
                _, bh = _draw_narration_box(draw, narr_x, bubble_y, lines, font_narr, max_bubble_w)
                bubble_y += bh + 8
            else:
                if char_id and char_id in char_names:
                    display = f"{char_names[char_id]}: {text}"
                else:
                    display = text

                lines = _wrap_text(display, font, max_bubble_w - 32)
                if speech_idx % 2 == 0:
                    bx = px + 10
                    tail = "left"
                else:
                    bx = px + pw - max_bubble_w - 10
                    tail = "right"

                _, bh = _draw_speech_bubble(draw, bx, bubble_y, lines, font, tail,
                                            max_bubble_w, mood)
                bubble_y += bh + 6
                speech_idx += 1

            if bubble_y > py + ph - 30:
                break

    final_path = output_dir / "final_page.png"
    page.save(final_path, "PNG")
    b64 = base64.b64encode(final_path.read_bytes()).decode()

    return {
        "path": str(final_path),
        "b64_preview": b64,
        "width": page.width,
        "height": page.height,
    }
