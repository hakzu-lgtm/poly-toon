"""표지 자동생성 — 캐릭터 시트 완성 후 핵심 장면 + 제목 합성"""

import base64
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from backend import factchat_client, config_store


def _load_font(size: int, bold: bool = True, font_path: str = "") -> ImageFont.FreeTypeFont:
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


def _draw_title(img: Image.Image, title: str, font_path: str = "") -> Image.Image:
    """표지 이미지 상단에 제목 텍스트를 합성."""
    draw = ImageDraw.Draw(img)
    w, h = img.size

    font_size = int(w * 0.07)
    font = _load_font(font_size, bold=True, font_path=font_path)

    bbox = font.getbbox(title)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # 너무 길면 폰트 줄이기
    while text_w > w * 0.85 and font_size > 20:
        font_size -= 4
        font = _load_font(font_size, bold=True, font_path=font_path)
        bbox = font.getbbox(title)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

    tx = (w - text_w) // 2
    ty = int(h * 0.06)
    pad_x, pad_y = 24, 16

    # 반투명 배경 박스
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [tx - pad_x, ty - pad_y, tx + text_w + pad_x, ty + text_h + pad_y],
        radius=16,
        fill=(0, 0, 0, 140),
    )
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")

    draw = ImageDraw.Draw(img)
    # 그림자
    draw.text((tx + 2, ty + 2), title, fill=(0, 0, 0), font=font)
    # 본문
    draw.text((tx, ty), title, fill=(255, 255, 255), font=font)

    return img


def generate_cover(
    story: dict,
    art_style: str,
    character_sheet_bytes: dict[str, bytes],
    project_dir: Path,
) -> dict:
    cfg = config_store.load()
    output_dir = project_dir / "cover"
    output_dir.mkdir(parents=True, exist_ok=True)

    cover_scene = story.get("cover_scene", "")
    if not cover_scene:
        cover_scene = (
            "Epic cover illustration featuring all main characters together, "
            "dramatic cinematic composition, title-page quality artwork"
        )

    characters = story.get("characters", [])
    char_descs = []
    for c in characters:
        char_descs.append(
            f"{c.get('name', '')}: {c.get('appearance', '')}, "
            f"wearing {c.get('outfit', '')}"
        )
    char_block = "; ".join(char_descs) if char_descs else ""

    prompt = (
        f"{art_style}, webtoon cover illustration, "
        f"{cover_scene}. "
        f"Characters: {char_block}. "
        f"Dynamic heroic composition, all characters prominently featured, "
        f"dramatic lighting, rich detailed background, "
        f"cover art quality, cinematic wide shot. "
        f"Leave clean empty space at the top for title text. "
        f"No text, no title, no letters, no watermarks."
    )

    ref_images = list(character_sheet_bytes.values())[:8]

    kw = dict(
        host=cfg["host"], api_key=cfg["api_key"],
        model=cfg["models"].get("image", factchat_client.DEFAULT_IMAGE_MODEL),
        size="1024x1536",
    )
    img_bytes = None
    if ref_images and factchat_client.use_reference_images():
        try:
            img_bytes = factchat_client.edit_image(ref_images, prompt, **kw)
        except factchat_client.CreditExhaustedError:
            raise
        except Exception:
            pass  # 참조 편집 실패 시 참조 없이 한 번만 생성
    if img_bytes is None:
        img_bytes = factchat_client.generate_image(prompt, **kw)

    # 제목 합성
    import io
    cover_img = Image.open(io.BytesIO(img_bytes))
    title = story.get("title", "")
    if title:
        cover_img = _draw_title(cover_img, title, cfg.get("font_path", ""))

    cover_path = output_dir / "cover.png"
    cover_img.save(str(cover_path), "PNG")
    final_bytes = cover_path.read_bytes()

    return {
        "path": str(cover_path),
        "b64_preview": base64.b64encode(final_bytes).decode(),
    }
