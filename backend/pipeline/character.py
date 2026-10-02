"""Stage 3: 캐릭터 시트 생성 — 1장에 다중 뷰 포함"""

import base64
from pathlib import Path
from backend import factchat_client, config_store

VIEWS = []


def _build_prompt(char: dict, art_style: str) -> str:
    return (
        f"ART STYLE (mandatory, apply to every view): {art_style}. "
        f"Render the whole sheet in exactly this art style, matching its rendering, colors and line quality; "
        f"do not fall back to a generic anime or sketch look. "
        f"Character reference sheet showing "
        f"multiple views of the SAME single character on a clean white background. "
        f"Layout: left side shows full body front view, "
        f"center shows full body three-quarter angle view, "
        f"right side shows a grid of 4 facial close-up expressions "
        f"(happy smile, surprised, angry, sad). "
        f"Character appearance: {char.get('appearance', '')}. "
        f"Outfit: {char.get('outfit', '')}. "
        f"All views must show the EXACT same character with consistent face, hair, body, and outfit. "
        f"Clean layout with clear spacing between views, "
        f"well-defined proportions, detailed face and clothing, all in the {art_style} look."
    )


def generate_character_sheet(
    character: dict, art_style: str, output_dir: Path, multi_view: bool = False
) -> dict:
    cfg = config_store.load()
    char_id = character.get("id", "char_unknown")
    output_dir.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(character, art_style)
    img_bytes = factchat_client.generate_image(
        prompt,
        host=cfg["host"],
        api_key=cfg["api_key"],
        model=cfg["models"].get("image", factchat_client.DEFAULT_IMAGE_MODEL),
        size="1536x1024",
    )

    fname = f"{char_id}_sheet.png"
    img_path = output_dir / fname
    img_path.write_bytes(img_bytes)

    return {
        "id": char_id,
        "name": character.get("name", ""),
        "views": [{
            "key": "sheet",
            "label": "캐릭터 시트",
            "path": str(img_path),
            "b64_preview": base64.b64encode(img_bytes).decode(),
        }],
        "primary_path": str(img_path),
    }


def generate_single_view(
    character: dict, art_style: str, output_dir: Path, view_key: str = "front"
) -> dict:
    return generate_character_sheet(character, art_style, output_dir)
