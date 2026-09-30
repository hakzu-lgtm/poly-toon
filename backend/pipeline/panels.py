"""Stage 4: 컷별 이미지 생성 — 자연스러운 웹툰 멀티프레임 레이아웃"""

import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from backend import factchat_client, config_store

CANVAS_W, CANVAS_H = 1024, 1536
GAP = 6
BORDER_COLOR = (255, 255, 255)
MAX_WORKERS = 4

# ── 레이아웃 정의 ─────────────────────────────────────────────
# 각 프레임: (x, y, w, h) — 캔버스 비율 (0.0~1.0)

LAYOUTS = {
    "1-full": [
        (0, 0, 1.0, 1.0),
    ],
    "2-row": [
        (0, 0, 1.0, 0.5),
        (0, 0.5, 1.0, 0.5),
    ],
    "2-col": [
        (0, 0, 0.5, 1.0),
        (0.5, 0, 0.5, 1.0),
    ],
    "3-row": [
        (0, 0, 1.0, 0.33),
        (0, 0.33, 1.0, 0.34),
        (0, 0.67, 1.0, 0.33),
    ],
    "3-col": [
        (0, 0, 0.33, 1.0),
        (0.33, 0, 0.34, 1.0),
        (0.67, 0, 0.33, 1.0),
    ],
    "1-big-2-small": [
        (0, 0, 1.0, 0.55),
        (0, 0.55, 0.5, 0.45),
        (0.5, 0.55, 0.5, 0.45),
    ],
    "2-small-1-big": [
        (0, 0, 0.5, 0.45),
        (0.5, 0, 0.5, 0.45),
        (0, 0.45, 1.0, 0.55),
    ],
    "1-big-3-small": [
        (0, 0, 1.0, 0.5),
        (0, 0.5, 0.33, 0.5),
        (0.33, 0.5, 0.34, 0.5),
        (0.67, 0.5, 0.33, 0.5),
    ],
    "side-main": [
        (0, 0, 0.35, 0.5),
        (0.35, 0, 0.65, 1.0),
        (0, 0.5, 0.35, 0.5),
    ],
    "diagonal-2": "diagonal",
}


def _best_gen_size(fw: int, fh: int) -> str:
    """프레임 비율에 맞는 최적 생성 사이즈."""
    ratio = fw / fh
    if ratio > 1.3:
        return "1536x1024"
    elif ratio < 0.77:
        return "1024x1536"
    return "1024x1024"


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
    frame: dict, panel: dict, characters: list[dict], art_style: str
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
        f"Cinematic composition, expressive, detailed. "
        f"No speech bubbles, no text."
    )


def _gen_frame_image(
    frame: dict, panel: dict, characters: list[dict], art_style: str,
    ref_images: list[bytes], gen_size: str, cfg: dict,
) -> Image.Image:
    """실패하면 예외를 그대로 올린다 — 회색 빈 이미지로 숨기지 않는다."""
    prompt = _build_frame_prompt(frame, panel, characters, art_style)
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
    if layout_key == "diagonal-2" and len(frames) == 2:
        return frames, layout_key
    regions = LAYOUTS.get(layout_key)
    if isinstance(regions, list) and len(regions) == len(frames):
        return frames, layout_key
    fallback = {1: "1-full", 2: "2-row", 3: "3-row", 4: "1-big-3-small"}
    return frames, fallback[len(frames)]


def _compose_standard(frame_images: list[Image.Image], layout_regions: list[tuple],
                       cw: int, ch: int) -> Image.Image:
    canvas = Image.new("RGB", (cw, ch), BORDER_COLOR)
    g = GAP

    for i, img in enumerate(frame_images):
        if i >= len(layout_regions):
            break
        rx, ry, rw, rh = layout_regions[i]
        px, py = int(rx * cw) + g, int(ry * ch) + g
        pw, ph = int(rw * cw) - g * 2, int(rh * ch) - g * 2
        if pw < 10 or ph < 10:
            continue
        cropped = _center_crop(img, pw, ph)
        canvas.paste(cropped, (px, py))

    return canvas


def _compose_diagonal(frame_images: list[Image.Image], cw: int, ch: int) -> Image.Image:
    """대각선 분할 합성."""
    canvas = Image.new("RGB", (cw, ch), BORDER_COLOR)

    if len(frame_images) < 2:
        if frame_images:
            canvas.paste(_center_crop(frame_images[0], cw, ch), (0, 0))
        return canvas

    img1 = _center_crop(frame_images[0], cw, ch)
    img2 = _center_crop(frame_images[1], cw, ch)

    mask = Image.new("L", (cw, ch), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon([(0, 0), (cw, 0), (cw, ch * 0.4), (0, ch * 0.7)], fill=255)

    canvas.paste(img2, (0, 0))
    canvas.paste(img1, (0, 0), mask)

    line_draw = ImageDraw.Draw(canvas)
    line_draw.line([(0, int(ch * 0.7)), (cw, int(ch * 0.4))],
                   fill=BORDER_COLOR, width=GAP)

    return canvas


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

    frames, layout_key = _fit_layout(frames, layout_key, cfg.get("max_frames_per_panel", 2))

    ref_images = []
    for cid in panel.get("characters_in_scene", []):
        if cid in character_sheets:
            ref_images.append(character_sheets[cid])

    is_diagonal = (layout_key == "diagonal-2")
    layout_regions = LAYOUTS.get(layout_key) if not is_diagonal else None

    if not is_diagonal and layout_regions is None:
        layout_regions = LAYOUTS["2-row"]

    variants = []
    for vi in range(variant_count):
        gen_sizes = []
        for frame in frames:
            if is_diagonal:
                gen_size = "1024x1536"
            elif layout_regions:
                idx = min(frame.get("frame", 1) - 1, len(layout_regions) - 1)
                rx, ry, rw, rh = layout_regions[idx]
                fw = int(rw * CANVAS_W)
                fh = int(rh * CANVAS_H)
                gen_size = _best_gen_size(fw, fh)
            else:
                gen_size = "1024x1024"
            gen_sizes.append(gen_size)

        with ThreadPoolExecutor(max_workers=min(len(frames), MAX_WORKERS)) as executor:
            frame_images = list(executor.map(
                lambda args: _gen_frame_image(args[0], panel, characters, art_style,
                                              ref_images, args[1], cfg),
                zip(frames, gen_sizes),
            ))

        if is_diagonal:
            composed = _compose_diagonal(frame_images, CANVAS_W, CANVAS_H)
        else:
            composed = _compose_standard(frame_images, layout_regions, CANVAS_W, CANVAS_H)

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
