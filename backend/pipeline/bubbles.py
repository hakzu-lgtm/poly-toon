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
    # 리눅스 서버 (Dockerfile에서 fonts-nanum 설치)
    if bold:
        candidates.append("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf")
    candidates.append("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── 말풍선 글꼴: 원스토어 모바일POP체 ─────────────────────────────
# 재배포가 금지된 글꼴이라 저장소에 넣지 않고, 처음 쓸 때 공식 배포처에서 받아 fonts/에 둔다.
POP_FONT_URL = "https://www.onestorecorp.com/assets/fonts/ONE%20Mobile%20POP.zip"
POP_FONT_NAME = "ONE Mobile POP.ttf"
FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"
TEXT_STROKE = 1   # 굵은 굵기가 없는 글꼴이라 테두리로 굵게 표시 (2배로 그려 줄이므로 실제로는 반 픽셀)


def _draw_bold_text(page, xy, text, font, color, anchor="la"):
    """2배 크기에 1px 테두리를 더해 그린 뒤 줄여 붙인다 → 뭉개지지 않고 적당히 굵은 글자."""
    path = getattr(font, "path", None)
    if not path:
        ImageDraw.Draw(page).text(xy, text, fill=color, font=font, anchor=anchor)
        return
    big = ImageFont.truetype(path, font.size * 2)
    l, t, r, b = big.getbbox(text, stroke_width=TEXT_STROKE, anchor=anchor)
    pad = 2
    layer = Image.new("L", (r - l + pad * 2, b - t + pad * 2), 0)
    ImageDraw.Draw(layer).text((pad - l, pad - t), text, font=big, fill=255, anchor=anchor,
                               stroke_width=TEXT_STROKE, stroke_fill=255)
    small = layer.resize(((layer.width + 1) // 2, (layer.height + 1) // 2), Image.LANCZOS)
    x, y = xy[0] + (l - pad) / 2, xy[1] + (t - pad) / 2
    page.paste(Image.new("RGB", small.size, color), (round(x), round(y)), small)


def _pop_font_path() -> str:
    candidates = [
        FONTS_DIR / POP_FONT_NAME,
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts" / POP_FONT_NAME,
        Path(r"C:\Windows\Fonts") / POP_FONT_NAME,
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    try:
        import io
        import zipfile
        import httpx
        r = httpx.get(POP_FONT_URL, timeout=30, follow_redirects=True)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = next(n for n in z.namelist() if n.endswith(POP_FONT_NAME) and "__MACOSX" not in n)
            FONTS_DIR.mkdir(exist_ok=True)
            (FONTS_DIR / POP_FONT_NAME).write_bytes(z.read(name))
        return str(FONTS_DIR / POP_FONT_NAME)
    except Exception:
        return ""  # 받지 못하면 기본 글꼴(맑은 고딕 굵게)


def _load_bubble_font(size: int, font_path: str = "") -> ImageFont.FreeTypeFont:
    """설정에서 글꼴을 지정했으면 그 글꼴, 아니면 모바일POP체."""
    if font_path.lower().endswith("malgun.ttf"):  # 예전 설정의 기본값은 지정하지 않은 것으로 본다
        font_path = ""
    return _load_font(size, bold=True, font_path=font_path or _pop_font_path())


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """띄어쓰기 단위로 줄바꿈. 한 어절이 줄보다 길 때만 글자 단위로 자른다."""
    def width(s):
        b = font.getbbox(s)
        return b[2] - b[0]

    lines, current = [], ""
    for word in text.split():
        test = f"{current} {word}" if current else word
        if width(test) <= max_width:
            current = test
            continue
        if current:
            lines.append(current)
        current = ""
        for ch in word:  # 너무 긴 어절
            if current and width(current + ch) > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
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


NAME_COLOR = "#2563EB"
PAD_X, PAD_Y = 16, 12
TAIL_ROOM = 16          # 말풍선 아래 꼬리가 차지하는 높이
NARR_PAD_Y = 10         # 나레이션 띠 위아래 여백
POS_GRID = 9            # 칸 안 말풍선 후보 위치 수 (각 축)


def _line_height(font) -> int:
    return font.getbbox("가")[3] - font.getbbox("가")[1] + 8


def _text_w(font, s: str) -> int:
    b = font.getbbox(s, stroke_width=TEXT_STROKE)
    return b[2] - b[0]


def _measure_bubble(lines, font, name, name_font):
    text_w = max((_text_w(font, l) for l in lines), default=50)
    name_w = _text_w(name_font, name) if name else 0
    name_h = (_line_height(name_font) + 2) if name else 0
    return max(text_w, name_w) + PAD_X * 2, name_h + _line_height(font) * len(lines) + PAD_Y * 2


def _draw_bubble(page, draw, x, y, lines, font, name, name_font, tail_dir, style):
    bw, bh = _measure_bubble(lines, font, name, name_font)
    BUBBLE_STYLES.get(style, BUBBLE_STYLES["normal"])(draw, x, y, bw, bh, tail_dir)
    ty = y + PAD_Y
    if name:  # 화자 이름: 말풍선 안 위쪽에 작게
        _draw_bold_text(page, (x + PAD_X, ty), name, name_font, NAME_COLOR)
        ty += _line_height(name_font) + 2
    color = TEXT_COLORS.get(style, TEXT_COLORS["normal"])
    for line in lines:
        _draw_bold_text(page, (x + PAD_X, ty), line, font, color)
        ty += _line_height(font)


def _point_in_poly(x, y, poly) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _rect_in_poly(r, poly) -> bool:
    x0, y0, x1, y1 = r
    pts = [(x0, y0), (x1, y0), (x0, y1), (x1, y1),
           ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]
    return all(_point_in_poly(px, py, poly) for px, py in pts)


def _overlap(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _place(bw, bh, poly, panel_rect, faces, placed, prev_in_frame):
    """얼굴·다른 말풍선과 겹침이 가장 적은 위치. 같은 칸의 다음 대사는 앞 대사보다 아래에."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    fx0, fy0, fx1, fy1 = min(xs) + 8, min(ys) + 8, max(xs) - 8, max(ys) - 8
    area = bw * bh
    best, best_cost = None, None
    for strict in (True, False):
        for i in range(POS_GRID):
            for j in range(POS_GRID):
                x = fx0 + (fx1 - fx0 - bw) * i / (POS_GRID - 1)
                y = fy0 + (fy1 - fy0 - bh - TAIL_ROOM) * j / (POS_GRID - 1)
                r = (x, y, x + bw, y + bh + TAIL_ROOM)
                if strict and not _rect_in_poly(r, poly):
                    continue
                if not strict:  # 칸에 안 들어가면 컷 안에서라도
                    px0, py0, px1, py1 = panel_rect
                    x = min(max(x, px0 + 6), px1 - bw - 6)
                    y = min(max(y, py0 + 6), py1 - bh - TAIL_ROOM - 6)
                    r = (x, y, x + bw, y + bh + TAIL_ROOM)
                cost = sum(_overlap(r, f) for f in faces) / area * 100
                cost += sum(_overlap(r, p) for p in placed) / area * 200
                if prev_in_frame and y < prev_in_frame[1] + 4:
                    cost += 5
                cost += (y - fy0) / max(fy1 - fy0, 1) * 0.5  # 같으면 위쪽 선호
                if best_cost is None or cost < best_cost:
                    best, best_cost = r, cost
        if best is not None:
            return best
    return best


def _tail_dir(rect, faces) -> str:
    """말풍선 꼬리를 가장 가까운 얼굴 쪽으로."""
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    if not faces:
        return "left"
    f = min(faces, key=lambda f: ((f[0] + f[2]) / 2 - cx) ** 2 + ((f[1] + f[3]) / 2 - cy) ** 2)
    return "left" if (f[0] + f[2]) / 2 < cx else "right"


def _frame_polys(pos) -> list:
    """컷 안 칸들의 다각형 (페이지 좌표). 레이아웃을 모르면 컷 전체를 한 칸으로."""
    from backend.pipeline import panels
    px, py, pw, ph = pos["x"], pos["y"], pos["width"], pos["height"]
    key = pos.get("layout")
    if key in panels.LAYOUTS:
        cw, ch = panels._canvas_size(key)
        if abs(ch / cw - ph / pw) < 0.02:
            s = pw / cw
            return [[(px + x * s, py + y * s) for x, y in poly] for poly in panels._frame_polygons(key)]
    return [[(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)]]


def _detect_page_faces(page, pos):
    from backend.pipeline import framing
    px, py, pw, ph = pos["x"], pos["y"], pos["width"], pos["height"]
    crop = page.crop((px, py, px + pw, py + ph))
    return [(px + x, py + y, px + x + w, py + y + h) for x, y, w, h, _ in framing.detect_faces(crop)]


def compose_bubbles(
    page_path: str,
    panel_positions: list[dict],
    story: dict,
    font_path: str = "",
    project_dir: Path = None,
) -> dict:
    """나레이션은 컷 위 자막 띠로, 대사는 칸별로 얼굴을 피해 말풍선으로 합성."""
    if project_dir is None:
        raise ValueError("project_dir required")

    output_dir = project_dir / "final"
    output_dir.mkdir(parents=True, exist_ok=True)

    src = Image.open(page_path).convert("RGB")
    W = src.width
    font = _load_bubble_font(19, font_path)
    name_font = _load_bubble_font(12, font_path)
    narr_font = _load_bubble_font(17, font_path)

    all_panels = []
    for ch in story.get("chapters", []):
        all_panels.extend(ch.get("panels", []))
    if not all_panels:
        all_panels = story.get("panels", [])
    panel_data = {p["panel_number"]: p for p in all_panels}
    char_names = {c["id"]: c["name"] for c in story.get("characters", [])}

    # 1) 나레이션 띠 높이 계산
    narr_w = int(W * 0.84)
    narr_lh = _line_height(narr_font)
    bands = {}
    for pos in panel_positions:
        dl = (panel_data.get(pos["panel_number"]) or {}).get("dialogue", [])
        lines = []
        for d in dl:
            if d.get("type") == "narration" and d.get("text"):
                lines += _wrap_text(d["text"], narr_font, narr_w - 32)
        if lines:
            bands[pos["panel_number"]] = (lines, len(lines) * narr_lh + 20 + NARR_PAD_Y * 2)

    # 2) 띠를 끼워 넣은 새 페이지
    positions = sorted(panel_positions, key=lambda p: p["y"])
    page = Image.new("RGB", (W, src.height + sum(h for _, h in bands.values())), "white")
    draw = ImageDraw.Draw(page)
    cursor = offset = 0
    new_positions = []
    for pos in positions:
        band = bands.get(pos["panel_number"])
        if band:
            page.paste(src.crop((0, cursor, W, pos["y"])), (0, cursor + offset))
            lines, bh = band
            box_w = max(_text_w(narr_font, l) for l in lines) + 32
            bx, by = (W - box_w) // 2, pos["y"] + offset + NARR_PAD_Y
            draw.rounded_rectangle([bx, by, bx + box_w, by + bh - NARR_PAD_Y * 2],
                                   radius=8, fill="#F1F5F9", outline="#CBD5E1", width=1)
            ty = by + 10
            for l in lines:
                _draw_bold_text(page, (W // 2, ty), l, narr_font, "#334155", anchor="ma")
                ty += narr_lh
            offset += bh
            cursor = pos["y"]
        new_positions.append({**pos, "y": pos["y"] + offset})
    page.paste(src.crop((0, cursor, W, src.height)), (0, cursor + offset))

    # 3) 대사 말풍선: 칸별로 나눠 얼굴을 피해 배치
    for pos in new_positions:
        panel = panel_data.get(pos["panel_number"])
        if not panel:
            continue
        speeches = [d for d in panel.get("dialogue", [])
                    if d.get("text") and d.get("type") != "narration"]
        if not speeches:
            continue

        polys = _frame_polys(pos)
        faces = _detect_page_faces(page, pos)
        panel_rect = (pos["x"], pos["y"], pos["x"] + pos["width"], pos["y"] + pos["height"])
        mood = _detect_mood(panel.get("mood", ""))
        placed, last_in_frame = [], {}

        for i, d in enumerate(speeches):
            fi = d.get("frame")
            fi = fi - 1 if isinstance(fi, int) and 1 <= fi <= len(polys) else i * len(polys) // len(speeches)
            poly = polys[fi]
            frame_w = max(p[0] for p in poly) - min(p[0] for p in poly)
            max_w = max(140, min(int(pos["width"] * 0.45), int(frame_w * 0.85)))

            name = char_names.get(d.get("character"), "")
            lines = _wrap_text(d["text"], font, max_w - PAD_X * 2)
            bw, bh = _measure_bubble(lines, font, name, name_font)
            rect = _place(bw, bh, poly, panel_rect, faces, placed, last_in_frame.get(fi))
            style = "thought" if d.get("type") == "thought" else mood
            _draw_bubble(page, draw, rect[0], rect[1], lines, font, name, name_font,
                         _tail_dir(rect, faces), style)
            placed.append(rect)
            last_in_frame[fi] = rect

    final_path = output_dir / "final_page.png"
    page.save(final_path, "PNG")
    b64 = base64.b64encode(final_path.read_bytes()).decode()

    return {
        "path": str(final_path),
        "b64_preview": b64,
        "width": page.width,
        "height": page.height,
    }
