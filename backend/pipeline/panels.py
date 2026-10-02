"""Stage 4: 컷별 이미지 생성 — 자연스러운 웹툰 멀티프레임 레이아웃"""

import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from backend import factchat_client, config_store

CANVAS_W = 1024          # 컷 캔버스 가로 (세로는 레이아웃마다 다름)
MARGIN = 14             # 캔버스 바깥 여백
GUTTER = 18             # 칸 사이 간격
LINE_W = 4              # 칸 테두리 두께
SS = 2                  # 사선 경계를 매끄럽게 그리기 위한 슈퍼샘플링 배율
BG_COLOR = (255, 255, 255)
LINE_COLOR = (20, 20, 20)
MAX_WORKERS = 4


def _rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


# ── 레이아웃 정의 ─────────────────────────────────────────────
# h: 캔버스 세로/가로 비율.  frames: 칸 다각형 (0.0~1.0 정규화 좌표, 칸 순서 = frame 순서)
# overlay: 다른 칸 위에 겹쳐 놓는 칸 번호(0부터).  use: 스토리 AI에게 주는 사용 지침

LAYOUTS = {
    # 1칸
    "1-wide": {
        "h": 0.62, "frames": [_rect(0, 0, 1, 1)],
        "use": "가로로 넓은 한 칸. 배경·상황 소개, 혼잣말, 조용한 한 장면",
    },
    "1-full": {
        "h": 1.25, "frames": [_rect(0, 0, 1, 1)],
        "use": "세로로 큰 한 칸. 클라이맥스·결심·결론처럼 강조할 장면, 큰 감정 표현",
    },
    # 2칸
    "2-row": {
        "h": 1.2, "frames": [_rect(0, 0, 1, 0.5), _rect(0, 0.5, 1, 0.5)],
        "use": "위아래 두 칸. 행동→결과, 원인→반응처럼 시간 흐름이 이어질 때",
    },
    "2-col": {
        "h": 0.72, "frames": [_rect(0, 0, 0.5, 1), _rect(0.5, 0, 0.5, 1)],
        "use": "좌우 두 칸. 두 인물의 대화 주고받기, 같은 순간의 두 표정 비교",
    },
    "2-col-slant": {
        "h": 0.72,
        "frames": [[(0, 0), (0.56, 0), (0.44, 1), (0, 1)],
                   [(0.56, 0), (1, 0), (1, 1), (0.44, 1)]],
        "use": "사선으로 나눈 좌우 두 칸. 대립·긴장, 빠른 대비(전/후, 나/상대)",
    },
    "diagonal-2": {
        "h": 1.2,
        "frames": [[(0, 0), (1, 0), (1, 0.4), (0, 0.6)],
                   [(0, 0.6), (1, 0.4), (1, 1), (0, 1)]],
        "use": "사선으로 나눈 위아래 두 칸. 갑작스러운 사건, 충격, 속도감 있는 전환",
    },
    "1-big-1-small": {
        "h": 1.15, "frames": [_rect(0, 0, 1, 0.64), _rect(0, 0.64, 1, 0.36)],
        "use": "큰 장면 아래 좁은 띠 한 칸. 큰 상황 뒤 손·물건 클로즈업이나 짧은 반응",
    },
    "inset": {
        "h": 1.0, "frames": [_rect(0, 0, 1, 1), _rect(0.6, 0.58, 0.36, 0.38)],
        "overlay": [1],
        "use": "큰 장면 모서리에 작은 칸을 겹침. 상황 속 인물의 표정·속마음 클로즈업",
    },
    # 3칸
    "3-row": {
        "h": 1.6,
        "frames": [_rect(0, 0, 1, 1 / 3), _rect(0, 1 / 3, 1, 1 / 3), _rect(0, 2 / 3, 1, 1 / 3)],
        "use": "위아래 세 칸. 같은 장소에서 행동→사건→반응이 차례로 일어날 때",
    },
    "3-col-slant": {
        "h": 0.55,
        "frames": [[(0, 0), (0.36, 0), (0.31, 1), (0, 1)],
                   [(0.36, 0), (0.70, 0), (0.65, 1), (0.31, 1)],
                   [(0.70, 0), (1, 0), (1, 1), (0.65, 1)]],
        "use": "사선으로 나눈 가로 띠 세 칸. 물건·장비 나열, 여러 대상을 한눈에 보여줄 때",
    },
    "3-row-slant": {
        "h": 1.3,
        "frames": [[(0, 0), (1, 0), (1, 0.30), (0, 0.36)],
                   [(0, 0.36), (1, 0.30), (1, 0.64), (0, 0.70)],
                   [(0, 0.70), (1, 0.64), (1, 1), (0, 1)]],
        "use": "사선으로 나눈 위아래 세 칸. 빠르게 이어지는 연속 동작(준비 과정, 착용 순서)",
    },
    "1-big-2-small": {
        "h": 1.3,
        "frames": [_rect(0, 0, 1, 0.56), _rect(0, 0.56, 0.5, 0.44), _rect(0.5, 0.56, 0.5, 0.44)],
        "use": "위 큰 장면 + 아래 작은 두 칸. 상황을 보여준 뒤 두 인물의 반응",
    },
    "2-small-1-big": {
        "h": 1.3,
        "frames": [_rect(0, 0, 0.5, 0.44), _rect(0.5, 0, 0.5, 0.44), _rect(0, 0.44, 1, 0.56)],
        "use": "위 작은 두 칸 + 아래 큰 장면. 작은 단서들이 쌓여 큰 결과로 이어질 때",
    },
    "side-main": {
        "h": 1.0,
        "frames": [_rect(0, 0, 0.38, 0.5), _rect(0.38, 0, 0.62, 1), _rect(0, 0.5, 0.38, 0.5)],
        "use": "오른쪽 세로로 긴 주인공 칸 + 왼쪽 작은 두 칸. 주인공 등장, 당당한 포즈",
    },
    # 4칸
    "4-grid": {
        "h": 1.0,
        "frames": [_rect(0, 0, 0.5, 0.5), _rect(0.5, 0, 0.5, 0.5),
                   _rect(0, 0.5, 0.5, 0.5), _rect(0.5, 0.5, 0.5, 0.5)],
        "use": "2×2 네 칸. 4컷 만화식 기승전결, 짧은 대화 여러 번",
    },
    "1-big-3-small": {
        "h": 1.2,
        "frames": [_rect(0, 0, 1, 0.55), _rect(0, 0.55, 1 / 3, 0.45),
                   _rect(1 / 3, 0.55, 1 / 3, 0.45), _rect(2 / 3, 0.55, 1 / 3, 0.45)],
        "use": "위 큰 장면 + 아래 작은 세 칸. 상황 뒤 세부 묘사나 여러 인물 반응",
    },
    "3-stack-1-tall": {
        "h": 0.95,
        "frames": [[(0, 0), (0.42, 0), (0.42, 0.30), (0, 0.36)],
                   [(0, 0.36), (0.42, 0.30), (0.42, 0.64), (0, 0.70)],
                   [(0, 0.70), (0.42, 0.64), (0.42, 1), (0, 1)],
                   _rect(0.42, 0, 0.58, 1)],
        "use": "왼쪽 사선 세 칸(준비 동작 클로즈업) + 오른쪽 세로로 긴 결과 칸. 준비 완료, 변신, 결심",
    },
}

# 예전 프로젝트에 저장된 레이아웃 이름 호환
LAYOUT_ALIASES = {"3-col": "3-col-slant"}
FALLBACK_LAYOUT = {1: "1-wide", 2: "2-row", 3: "3-row", 4: "4-grid"}


def layout_guide(max_frames: int) -> str:
    """스토리 AI 프롬프트용: 사용 가능한 레이아웃 목록."""
    lines = []
    for key, spec in LAYOUTS.items():
        n = len(spec["frames"])
        if n <= max_frames:
            lines.append(f'  - "{key}" ({n}칸): {spec["use"]}')
    return "\n".join(lines)


def _signed_area(pts):
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n)) / 2


def _inset_polygon(pts, d):
    """볼록 다각형의 각 변을 안쪽으로 d만큼 평행 이동한 다각형 (d<0이면 바깥쪽)."""
    n = len(pts)
    sign = 1 if _signed_area(pts) > 0 else -1
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5 or 1
        nx, ny = -dy / length * sign, dx / length * sign
        lines.append(((x1 + nx * d, y1 + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (px, py), (rx, ry) = lines[i - 1]
        (qx, qy), (sx, sy) = lines[i]
        denom = rx * sy - ry * sx
        if abs(denom) < 1e-9:
            out.append((qx, qy))
            continue
        t = ((qx - px) * sy - (qy - py) * sx) / denom
        out.append((px + t * rx, py + t * ry))
    return out


def _canvas_size(layout_key: str) -> tuple[int, int]:
    return CANVAS_W, int(CANVAS_W * LAYOUTS[layout_key]["h"])


def _frame_polygons(layout_key: str, scale: int = 1) -> list[list[tuple[float, float]]]:
    """레이아웃의 칸들을 픽셀 좌표 다각형으로 (여백·간격 반영)."""
    spec = LAYOUTS[layout_key]
    cw, ch = _canvas_size(layout_key)
    m, g = MARGIN * scale, GUTTER * scale
    iw, ih = cw * scale - 2 * m, ch * scale - 2 * m
    overlay = set(spec.get("overlay", []))
    polys = []
    for i, frame in enumerate(spec["frames"]):
        pts = [(m + x * iw, m + y * ih) for x, y in frame]
        polys.append(pts if i in overlay else _inset_polygon(pts, g / 2))
    return polys


def _bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return int(min(xs)), int(min(ys)), int(max(xs) + 0.999), int(max(ys) + 0.999)


def _best_gen_size(fw: float, fh: float) -> str:
    """프레임 비율에 맞는 최적 생성 사이즈."""
    ratio = fw / fh
    if ratio > 1.3:
        return "1536x1024"
    elif ratio < 0.77:
        return "1024x1536"
    return "1024x1024"


def _framing_hint(fw: float, fh: float) -> str:
    ratio = fw / fh
    if ratio > 1.6:
        return "wide horizontal framing"
    if ratio < 0.7:
        return "tall vertical framing"
    return "balanced framing"


def _center_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """이미지를 왜곡 없이 중앙 크롭. 비율 유지."""
    iw, ih = img.size
    target_ratio = target_w / target_h
    img_ratio = iw / ih

    if img_ratio > target_ratio:
        new_w = int(ih * target_ratio)
        left = (iw - new_w) // 2
        img = img.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target_ratio)
        top = (ih - new_h) // 2
        img = img.crop((0, top, iw, top + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _build_frame_prompt(
    frame: dict, panel: dict, characters: list[dict], art_style: str, framing: str = ""
) -> str:
    char_descs = []
    for cid in panel.get("characters_in_scene", []):
        char = next((c for c in characters if c["id"] == cid), None)
        if char:
            char_descs.append(
                f"{char['name']}: {char.get('appearance', '')}, "
                f"wearing {char.get('outfit', '')}"
            )
    char_block = "; ".join(char_descs) if char_descs else ""
    shot = frame.get("shot_type", "medium shot")

    return (
        f"{art_style}, webtoon panel, "
        f"{shot}, {frame.get('scene', '')}. "
        f"Characters: {char_block}. "
        f"Mood: {panel.get('mood', 'neutral')}. "
        f"Cinematic composition, {framing or 'balanced framing'}, "
        f"main subject kept near the center with some margin around it, expressive, detailed. "
        f"A single continuous scene filling the whole image: no panel borders, no comic grid, "
        f"no speech bubbles, no text."
    )


def _gen_frame_image(
    frame: dict, panel: dict, characters: list[dict], art_style: str,
    ref_images: list[bytes], gen_size: str, framing: str, cfg: dict,
) -> Image.Image:
    """실패하면 예외를 그대로 올린다 — 회색 빈 이미지로 숨기지 않는다."""
    prompt = _build_frame_prompt(frame, panel, characters, art_style, framing)
    kw = dict(
        host=cfg["host"], api_key=cfg["api_key"],
        model=cfg["models"].get("image", factchat_client.DEFAULT_IMAGE_MODEL),
        size=gen_size,
    )
    if ref_images and factchat_client.use_reference_images():
        try:
            img_bytes = factchat_client.edit_image(ref_images, prompt, **kw)
            return Image.open(io.BytesIO(img_bytes))
        except factchat_client.CreditExhaustedError:
            raise
        except Exception:
            pass  # 참조 편집 실패 시 참조 없이 한 번만 생성
    img_bytes = factchat_client.generate_image(prompt, **kw)
    return Image.open(io.BytesIO(img_bytes))


def _fit_layout(frames: list[dict], layout_key: str, max_frames: int) -> tuple[list[dict], str]:
    """칸 수를 max_frames 이하로 자르고, 남은 칸 수에 맞는 레이아웃을 고른다."""
    frames = frames[:max_frames]
    layout_key = LAYOUT_ALIASES.get(layout_key, layout_key)
    spec = LAYOUTS.get(layout_key)
    if spec and len(spec["frames"]) == len(frames):
        return frames, layout_key
    return frames, FALLBACK_LAYOUT[len(frames)]


def _compose(frame_images: list[Image.Image], layout_key: str) -> Image.Image:
    """칸 이미지를 레이아웃 다각형 모양으로 잘라 넣고 테두리를 그린다."""
    cw, ch = _canvas_size(layout_key)
    canvas = Image.new("RGB", (cw * SS, ch * SS), BG_COLOR)
    draw = ImageDraw.Draw(canvas)
    overlay = set(LAYOUTS[layout_key].get("overlay", []))

    for i, (img, pts) in enumerate(zip(frame_images, _frame_polygons(layout_key, SS))):
        x0, y0, x1, y1 = _bbox(pts)
        if x1 - x0 < 10 or y1 - y0 < 10:
            continue
        if i in overlay:  # 겹친 칸은 흰 여백으로 아래 칸과 분리
            draw.polygon(_inset_polygon(pts, -GUTTER * SS / 2), fill=BG_COLOR)
        mask = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(mask).polygon([(x - x0, y - y0) for x, y in pts], fill=255)
        canvas.paste(_center_crop(img.convert("RGB"), x1 - x0, y1 - y0), (x0, y0), mask)
        draw.line(pts + [pts[0]], fill=LINE_COLOR, width=LINE_W * SS, joint="curve")

    return canvas.resize((cw, ch), Image.LANCZOS)


def generate_panel_variants(
    panel: dict,
    characters: list[dict],
    art_style: str,
    character_sheets: dict[str, bytes],
    output_dir: Path,
    variant_count: int = 1,
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = config_store.load()
    panel_num = panel.get("panel_number", 0)

    frames = panel.get("frames", [])
    layout_key = panel.get("layout", "2-row")

    if not frames:
        scene = panel.get("scene", "")
        frames = [
            {"frame": 1, "shot_type": "wide shot", "scene": scene},
            {"frame": 2, "shot_type": "close-up",
             "scene": scene + ", focusing on character facial expression and emotion"},
        ]
        layout_key = "2-row"

    frames, layout_key = _fit_layout(frames, layout_key, cfg.get("max_frames_per_panel", 3))

    ref_images = []
    for cid in panel.get("characters_in_scene", []):
        if cid in character_sheets:
            ref_images.append(character_sheets[cid])

    gen_sizes, framings = [], []
    for pts in _frame_polygons(layout_key):
        x0, y0, x1, y1 = _bbox(pts)
        gen_sizes.append(_best_gen_size(x1 - x0, y1 - y0))
        framings.append(_framing_hint(x1 - x0, y1 - y0))

    variants = []
    for vi in range(variant_count):
        with ThreadPoolExecutor(max_workers=min(len(frames), MAX_WORKERS)) as executor:
            frame_images = list(executor.map(
                lambda args: _gen_frame_image(args[0], panel, characters, art_style,
                                              ref_images, args[1], args[2], cfg),
                zip(frames, gen_sizes, framings),
            ))

        composed = _compose(frame_images, layout_key)

        fname = f"panel_{panel_num:02d}_v{vi}.png"
        out_path = output_dir / fname
        composed.save(str(out_path), "PNG")

        variants.append({
            "variant": vi,
            "path": str(out_path),
            "b64_preview": base64.b64encode(out_path.read_bytes()).decode(),
        })

    return variants


def generate_all_panels(
    story: dict,
    art_style: str,
    character_sheets: dict[str, bytes],
    project_dir: Path,
    variant_count: int = 1,
) -> list[dict]:
    output_dir = project_dir / "panels"
    output_dir.mkdir(parents=True, exist_ok=True)

    characters = story.get("characters", [])
    all_panels = []
    for ch in story.get("chapters", []):
        all_panels.extend(ch.get("panels", []))
    if not all_panels:
        all_panels = story.get("panels", [])

    results = []
    for panel in all_panels:
        variants = generate_panel_variants(
            panel, characters, art_style,
            character_sheets, output_dir, variant_count,
        )
        first_scene = ""
        frs = panel.get("frames", [])
        if frs:
            first_scene = frs[0].get("scene", "")
        else:
            first_scene = panel.get("scene", "")

        results.append({
            "panel_number": panel.get("panel_number", 0),
            "scene": first_scene,
            "variants": variants,
            "selected": 0,
        })

    return results
