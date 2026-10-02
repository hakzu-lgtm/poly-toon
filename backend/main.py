import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend import config_store, factchat_client, usage_tracker, project_store
from backend.pipeline import story as story_pipeline
from backend.pipeline import character as char_pipeline
from backend.pipeline import panels as panels_pipeline
from backend.pipeline import cover as cover_pipeline
from backend.pipeline import layout as layout_pipeline
from backend.pipeline import bubbles as bubbles_pipeline
from backend.pipeline import exporter

app = FastAPI(title="웹툰 메이커", version="0.1.0")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Stage 0: 설정 / 연결 ───────────────────────────────────────

class ConfigBody(BaseModel):
    host: str = "https://factchat-cloud.mindlogic.ai"
    api_key: str = ""
    models: dict | None = None
    font_path: str | None = None
    image_quality: str | None = None
    max_frames_per_panel: int | None = None
    use_reference_images: bool | None = None


@app.get("/api/config")
async def get_config():
    cfg = config_store.load()
    return {
        "host": cfg["host"],
        "api_key_masked": config_store.mask_key(cfg.get("api_key", "")),
        "has_key": bool(cfg.get("api_key")),
        "models": cfg["models"],
        "font_path": cfg.get("font_path", ""),
        "image_quality": cfg.get("image_quality", "medium"),
        "max_frames_per_panel": cfg.get("max_frames_per_panel", 3),
        "use_reference_images": cfg.get("use_reference_images", False),
    }


@app.post("/api/config")
async def save_config(body: ConfigBody):
    cfg = config_store.load()
    cfg["host"] = body.host.strip()
    if body.api_key:
        cfg["api_key"] = body.api_key.strip()
    if body.models:
        cfg["models"] = {**cfg["models"], **body.models}
    if body.font_path:
        cfg["font_path"] = body.font_path.strip()
    if body.image_quality in factchat_client.IMAGE_QUALITIES:
        cfg["image_quality"] = body.image_quality
    if body.max_frames_per_panel in (1, 2, 3, 4):
        cfg["max_frames_per_panel"] = body.max_frames_per_panel
    if body.use_reference_images is not None:
        cfg["use_reference_images"] = body.use_reference_images
    config_store.save(cfg)
    return {
        "ok": True,
        "api_key_masked": config_store.mask_key(cfg["api_key"]),
    }


@app.post("/api/test-connection")
async def test_connection():
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")
    result = factchat_client.test_connection(
        cfg["host"], cfg["api_key"],
        image_model=cfg["models"].get("image", factchat_client.DEFAULT_IMAGE_MODEL),
    )
    return result


@app.get("/api/usage")
async def get_usage():
    return usage_tracker.load()


# ── 그림체 미리보기 ───────────────────────────────────────────────

STYLE_PREVIEW_DIR = OUTPUTS_DIR / "style_previews"
STYLE_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

ART_STYLES = [
    {"key": "soft_cel", "label": "소프트 셀셰이딩", "prompt": "soft cel-shaded webtoon style, clean lineart, pastel palette"},
    {"key": "vivid_anime", "label": "비비드 애니메이션", "prompt": "vibrant anime style, bold colors, dynamic poses, sharp details"},
    {"key": "realistic", "label": "리얼리스틱 실사풍", "prompt": "hyper-realistic photographic style, cinematic lighting, lifelike skin textures, shallow depth of field"},
    {"key": "claymation", "label": "클레이 애니메이션", "prompt": "claymation style, 3D clay figures, soft rounded shapes, stop-motion texture, handcrafted feel"},
    {"key": "marvel", "label": "마블 코믹 스타일", "prompt": "Marvel comic book style, dramatic shading, bold ink outlines, heroic poses, dynamic action panels"},
    {"key": "ghibli", "label": "지브리 스타일", "prompt": "Studio Ghibli style, warm watercolor tones, lush detailed backgrounds, gentle character designs"},
    {"key": "minimal_flat", "label": "미니멀 플랫", "prompt": "minimal flat illustration, simple geometric shapes, muted earth-tone colors, clean design"},
    {"key": "pixel_art", "label": "레트로 픽셀아트", "prompt": "retro pixel art style, 16-bit aesthetic, pixelated characters, nostalgic color palette"},
    {"key": "watercolor", "label": "수채화풍", "prompt": "watercolor painting style, soft bleeding edges, translucent washes, artistic brush strokes"},
    {"key": "chibi", "label": "큐트 치비", "prompt": "cute chibi style, oversized heads, round shapes, bright candy colors, kawaii aesthetic"},
    {"key": "noir", "label": "느와르 그래픽노블", "prompt": "noir graphic novel style, high contrast black and white, dramatic shadows, gritty textures"},
    {"key": "disney_3d", "label": "디즈니 3D", "prompt": "Disney 3D animation style, smooth CGI rendering, expressive faces, vibrant saturated colors"},
]

STYLE_PREVIEW_PROMPT = (
    "22-year-old female college student named Nana, "
    "wearing a casual white t-shirt and denim shorts, "
    "full body standing shot, cute face with bright cheerful expression, "
    "wavy brown hair flowing down to shoulders, "
    "clean simple background, single character"
)


@app.get("/api/style-previews")
async def get_style_previews():
    results = []
    for s in ART_STYLES:
        img_path = STYLE_PREVIEW_DIR / f"{s['key']}.png"
        results.append({
            "key": s["key"],
            "label": s["label"],
            "prompt": s["prompt"],
            "has_preview": img_path.exists(),
        })
    return {"styles": results}


@app.post("/api/style-previews/generate-stream")
async def generate_style_previews_stream():
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")

    async def event_stream():
        import base64
        total = len(ART_STYLES)
        for i, style in enumerate(ART_STYLES):
            img_path = STYLE_PREVIEW_DIR / f"{style['key']}.png"
            if img_path.exists():
                b64 = base64.b64encode(img_path.read_bytes()).decode()
                yield f"data: {json.dumps({'type': 'style', 'current': i+1, 'total': total, 'key': style['key'], 'label': style['label'], 'b64': b64}, ensure_ascii=False)}\n\n"
                continue

            prompt = f"{style['prompt']}, {STYLE_PREVIEW_PROMPT}"
            try:
                img_bytes = await asyncio.to_thread(
                    factchat_client.generate_image,
                    prompt,
                    host=cfg["host"],
                    api_key=cfg["api_key"],
                    model=cfg["models"].get("image", factchat_client.DEFAULT_IMAGE_MODEL),
                    size="1024x1024",
                )
                img_path.write_bytes(img_bytes)
                b64 = base64.b64encode(img_bytes).decode()
                yield f"data: {json.dumps({'type': 'style', 'current': i+1, 'total': total, 'key': style['key'], 'label': style['label'], 'b64': b64}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'current': i+1, 'total': total, 'key': style['key'], 'error': str(e)}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Stage 1: 웹툰 설정 ───────────────────────────────────────────

class ChapterConfig(BaseModel):
    chapter: int
    panel_count: int = 6

class WebtoonSettings(BaseModel):
    keywords: str
    genre: str
    mood: str
    art_style: str
    chapter_count: int = 1
    chapters_config: list[ChapterConfig] = []
    panel_count: int = 6
    character_count: int = 2
    dialogue_tone: str = "자연스러운 일상체"
    canvas_width: int = 800
    extra_notes: str = ""


_current_settings: dict = {}
_current_story: dict = {}
_character_sheets: list[dict] = []
_character_sheet_bytes: dict[str, bytes] = {}
_panel_results: list[dict] = []
_cover_result: dict = {}
_layout_result: dict = {}
_bubble_result: dict = {}


_SETTINGS_FILE = OUTPUTS_DIR / "current" / "_settings.json"
_STORY_FILE = OUTPUTS_DIR / "current" / "_story.json"


def _persist_settings():
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(_current_settings, ensure_ascii=False), encoding="utf-8")


def _persist_story():
    _STORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STORY_FILE.write_text(json.dumps(_current_story, ensure_ascii=False), encoding="utf-8")


def _load_persisted():
    global _current_settings, _current_story, _character_sheets, _character_sheet_bytes
    if _SETTINGS_FILE.exists():
        _current_settings = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    if _STORY_FILE.exists():
        _current_story = json.loads(_STORY_FILE.read_text(encoding="utf-8"))
    # 캐릭터 시트 파일 자동 복원
    chars_dir = OUTPUTS_DIR / "current" / "characters"
    if chars_dir.exists():
        for f in chars_dir.glob("*_sheet.png"):
            cid = f.stem.replace("_sheet", "")
            _character_sheet_bytes[cid] = f.read_bytes()
            char_info = next(
                (c for c in _current_story.get("characters", []) if c.get("id") == cid),
                {"id": cid, "name": cid},
            )
            import base64
            _character_sheets.append({
                "id": cid,
                "name": char_info.get("name", cid),
                "views": [{"key": "sheet", "label": "캐릭터 시트",
                           "path": str(f),
                           "b64_preview": base64.b64encode(f.read_bytes()).decode()}],
                "primary_path": str(f),
            })

_load_persisted()

_PANELS_FILE = OUTPUTS_DIR / "current" / "_panels.json"


def _persist_panels():
    """컷 목록(파일 경로·선택)을 디스크에 남겨 서버를 재시작해도 4단계가 비지 않게 한다."""
    _PANELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [{
        "panel_number": pr["panel_number"],
        "scene": pr.get("scene", ""),
        "selected": pr.get("selected", 0),
        "variants": [{k: v[k] for k in ("variant", "path", "layout") if k in v}
                     for v in pr.get("variants", [])],
    } for pr in _panel_results]
    _PANELS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _load_panels():
    global _panel_results
    results = []
    if _PANELS_FILE.exists():
        for pr in json.loads(_PANELS_FILE.read_text(encoding="utf-8")):
            pr["variants"] = [v for v in pr.get("variants", []) if Path(v["path"]).exists()]
            if pr["variants"]:
                pr["selected"] = min(pr.get("selected", 0), len(pr["variants"]) - 1)
                results.append(pr)
    elif _STORY_FILE.exists():
        # 목록 파일이 생기기 전 작업: 현재 스토리 이후에 만들어진 컷 파일로 복원
        story_time = _STORY_FILE.stat().st_mtime
        panels_dir = OUTPUTS_DIR / "current" / "panels"
        by_num: dict[int, list] = {}
        for f in sorted(panels_dir.glob("panel_*_v*.png")) if panels_dir.exists() else []:
            if f.stat().st_mtime < story_time:
                continue
            _, num, var = f.stem.split("_")
            by_num.setdefault(int(num), []).append({"variant": int(var[1:]), "path": str(f)})
        for num in sorted(by_num):
            results.append({"panel_number": num, "scene": "", "selected": 0,
                            "variants": sorted(by_num[num], key=lambda v: v["variant"])})
    _panel_results = results


_load_panels()


def _clear_character_sheets():
    """새 스토리를 만들면 이전 스토리의 캐릭터 시트·표지는 쓰지 않는다 (저장된 프로젝트 폴더는 그대로)."""
    global _character_sheets, _character_sheet_bytes, _cover_result
    _character_sheets = []
    _character_sheet_bytes = {}
    _cover_result = {}
    chars_dir = OUTPUTS_DIR / "current" / "characters"
    if chars_dir.exists():
        for f in chars_dir.glob("*_sheet.png"):
            f.unlink(missing_ok=True)


@app.post("/api/stage1/settings")
async def save_settings(body: WebtoonSettings):
    global _current_settings
    _current_settings = body.model_dump()
    _persist_settings()
    return {"ok": True, "settings": _current_settings}


@app.get("/api/stage1/settings")
async def get_settings():
    return _current_settings or {}


# ── Stage 2: 스토리 생성 ─────────────────────────────────────────

@app.post("/api/stage2/generate")
async def generate_story():
    global _current_story
    if not _current_settings:
        raise HTTPException(400, "Stage 1 설정이 필요합니다.")
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다. Stage 0에서 키를 먼저 저장하세요.")
    try:
        _current_story = await asyncio.to_thread(
            story_pipeline.generate_story, _current_settings
        )
        _persist_story()
        _clear_character_sheets()
        _panel_results.clear()
        _persist_panels()
        return _current_story
    except Exception as e:
        raise HTTPException(500, f"스토리 생성 실패: {e}")


@app.get("/api/stage2/story")
async def get_story():
    return _current_story or {}


@app.put("/api/stage2/story")
async def update_story(body: dict):
    global _current_story
    _current_story = body
    _persist_story()
    return {"ok": True}


# ── Stage 3: 캐릭터 시트 (SSE 스트리밍) ──────────────────────────

def _make_thumbnail_b64(b64_full: str, max_w: int = 400) -> str:
    """큰 이미지를 축소한 base64 썸네일로 변환."""
    import base64 as b64mod
    from PIL import Image
    import io
    raw = b64mod.b64decode(b64_full)
    img = Image.open(io.BytesIO(raw))
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return b64mod.b64encode(buf.getvalue()).decode()


def _safe_char(s: dict) -> dict:
    views = []
    for v in s.get("views", []):
        try:
            p = Path(v.get("path", "")).resolve()
            # 같은 파일명으로 다시 생성해도 브라우저가 예전 이미지를 쓰지 않도록 수정 시각을 붙인다
            url = ("/outputs/" + p.relative_to(OUTPUTS_DIR.resolve()).as_posix()
                   + f"?v={p.stat().st_mtime_ns}")
        except (ValueError, TypeError, OSError):
            url = ""
        views.append({"key": v["key"], "label": v["label"], "url": url})
    return {"id": s["id"], "name": s["name"], "views": views}


@app.post("/api/stage3/generate-stream")
async def generate_characters_stream():
    if not _current_story or not _current_story.get("characters"):
        raise HTTPException(400, "Stage 2 스토리가 필요합니다.")
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")

    art_style = _current_settings.get("art_style", "webtoon style")
    project_dir = OUTPUTS_DIR / "current"
    characters = _current_story["characters"]

    async def event_stream():
        global _character_sheets, _character_sheet_bytes, _cover_result
        _character_sheets = []
        _character_sheet_bytes = {}
        total_chars = len(characters)
        total_steps = total_chars + 1
        step = 0

        for ci, char in enumerate(characters):
            step += 1
            char_name = char.get("name", f"캐릭터 {ci+1}")
            msg = f"{char_name} 캐릭터 시트 생성 중... ({step}/{total_steps})"
            yield f"data: {json.dumps({'type': 'progress', 'current': step, 'total': total_steps, 'message': msg}, ensure_ascii=False)}\n\n"

            try:
                result = await asyncio.to_thread(
                    char_pipeline.generate_character_sheet,
                    char, art_style, project_dir / "characters", False
                )
                _character_sheets.append(result)

                views = result.get("views", [])
                if views:
                    p = Path(views[0]["path"])
                    if p.exists():
                        _character_sheet_bytes[result["id"]] = p.read_bytes()

                yield f"data: {json.dumps({'type': 'character', 'current': ci + 1, 'total': total_chars, 'data': _safe_char(result)}, ensure_ascii=False)}\n\n"
            except factchat_client.CreditExhaustedError as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'생성을 중단했습니다. {e}'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'{char_name} 생성 실패: {str(e)}'}, ensure_ascii=False)}\n\n"

        # 표지 자동생성
        yield f"data: {json.dumps({'type': 'progress', 'message': '표지 이미지 생성 중...'}, ensure_ascii=False)}\n\n"
        try:
            _cover_result = await asyncio.to_thread(
                cover_pipeline.generate_cover,
                _current_story, art_style, _character_sheet_bytes, project_dir,
            )
            cover_rel = Path(_cover_result['path']).resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
            cover_rel += f"?v={Path(_cover_result['path']).stat().st_mtime_ns}"
            yield f"data: {json.dumps({'type': 'cover', 'url': f'/outputs/{cover_rel}'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'cover_error', 'error': str(e)}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/stage3/regenerate/{char_id}")
async def regenerate_character(char_id: str):
    global _character_sheets, _character_sheet_bytes
    char = next((c for c in _current_story.get("characters", []) if c["id"] == char_id), None)
    if not char:
        raise HTTPException(404, f"캐릭터 {char_id}를 찾을 수 없습니다.")
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")

    art_style = _current_settings.get("art_style", "webtoon style")
    project_dir = OUTPUTS_DIR / "current"
    try:
        result = char_pipeline.generate_character_sheet(char, art_style, project_dir / "characters")
        for i, cs in enumerate(_character_sheets):
            if cs["id"] == char_id:
                _character_sheets[i] = result
                break
        else:
            _character_sheets.append(result)

        front = result["views"][0] if result["views"] else None
        if front:
            p = Path(front["path"])
            if p.exists():
                _character_sheet_bytes[char_id] = p.read_bytes()

        return _safe_char(result)
    except Exception as e:
        raise HTTPException(500, f"캐릭터 재생성 실패: {e}")


@app.post("/api/stage3/regenerate-cover")
async def regenerate_cover():
    global _cover_result
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")
    art_style = _current_settings.get("art_style", "webtoon style")
    project_dir = OUTPUTS_DIR / "current"
    try:
        _cover_result = cover_pipeline.generate_cover(
            _current_story, art_style, _character_sheet_bytes, project_dir,
        )
        return {"b64_preview": _cover_result["b64_preview"]}
    except Exception as e:
        raise HTTPException(500, f"표지 재생성 실패: {e}")


@app.get("/api/stage3/sheets")
async def get_character_sheets():
    return {
        "characters": [_safe_char(s) for s in _character_sheets],
        "cover": {"b64_preview": _cover_result.get("b64_preview", "")} if _cover_result else None,
    }


# ── Stage 4: 컷 이미지 (SSE 스트리밍 + 개별 재생성) ─────────────

class PanelGenRequest(BaseModel):
    variant_count: int = 1


def _all_panels(story: dict) -> list[dict]:
    """장 기반 구조에서 모든 패널을 플랫하게 추출."""
    panels = []
    for ch in story.get("chapters", []):
        panels.extend(ch.get("panels", []))
    if not panels:
        panels = story.get("panels", [])
    return panels


@app.post("/api/stage4/generate-stream")
async def generate_panels_stream(body: PanelGenRequest):
    if not _current_story:
        raise HTTPException(400, "Stage 2 스토리가 필요합니다.")
    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")

    art_style = _current_settings.get("art_style", "webtoon style")
    project_dir = OUTPUTS_DIR / "current"
    panels = _all_panels(_current_story)
    characters = _current_story.get("characters", [])

    async def event_stream():
        global _panel_results
        _panel_results = []
        total = len(panels)

        for pi, panel in enumerate(panels):
            pn = panel.get("panel_number", pi + 1)
            yield f"data: {json.dumps({'type': 'progress', 'current': pi + 1, 'total': total, 'panel_number': pn}, ensure_ascii=False)}\n\n"

            try:
                variants = await asyncio.to_thread(
                    panels_pipeline.generate_panel_variants,
                    panel, characters, art_style,
                    _character_sheet_bytes, project_dir / "panels", body.variant_count,
                )

                frames = panel.get("frames", [])
                scene_text = panel.get("scene", "")
                if not scene_text and frames:
                    scene_text = frames[0].get("scene", "")

                result = {
                    "panel_number": pn,
                    "scene": scene_text,
                    "variants": variants,
                    "selected": 0,
                }
                _panel_results.append(result)
                _persist_panels()

                safe_variants = []
                for v in variants:
                    try:
                        rel_path = Path(v["path"]).resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
                    except ValueError:
                        rel_path = Path(v["path"]).name
                    safe_variants.append({"variant": v["variant"],
                                          "url": f"/outputs/{rel_path}?v={Path(v['path']).stat().st_mtime_ns}"})
                yield f"data: {json.dumps({'type': 'panel', 'panel_number': pn, 'scene': result['scene'], 'variants': safe_variants, 'selected': 0}, ensure_ascii=False)}\n\n"
            except factchat_client.CreditExhaustedError as e:
                yield f"data: {json.dumps({'type': 'error', 'panel_number': pn, 'message': f'컷 {pn}에서 생성을 중단했습니다. {e}'}, ensure_ascii=False)}\n\n"
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'panel_number': pn, 'message': f'컷 {pn} 생성 실패: {str(e)}'}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class PanelSelectRequest(BaseModel):
    panel_number: int
    selected: int


@app.post("/api/stage4/select")
async def select_panel_variant(body: PanelSelectRequest):
    for pr in _panel_results:
        if pr["panel_number"] == body.panel_number:
            pr["selected"] = body.selected
            _persist_panels()
            return {"ok": True}
    raise HTTPException(404, "해당 컷을 찾을 수 없습니다.")


class PanelRegenRequest(BaseModel):
    panel_number: int
    custom_prompt: str = ""


@app.post("/api/stage4/regenerate")
async def regenerate_single_panel(body: PanelRegenRequest):
    panels = _all_panels(_current_story)
    panel = next((p for p in panels if p.get("panel_number") == body.panel_number), None)
    if not panel:
        raise HTTPException(404, "해당 컷을 찾을 수 없습니다.")

    cfg = config_store.load()
    if not cfg.get("api_key"):
        raise HTTPException(400, "API 키가 설정되지 않았습니다.")

    art_style = _current_settings.get("art_style", "webtoon style")
    project_dir = OUTPUTS_DIR / "current"
    characters = _current_story.get("characters", [])

    if body.custom_prompt:
        extra = f". Additional direction: {body.custom_prompt}"
        if panel.get("frames"):
            panel = {**panel, "frames": [{**f, "scene": f.get("scene", "") + extra}
                                         for f in panel["frames"]]}
        else:
            panel = {**panel, "scene": body.custom_prompt}

    pr = next((p for p in _panel_results if p["panel_number"] == body.panel_number), None)
    start = max((v["variant"] for v in pr["variants"]), default=-1) + 1 if pr else 0

    try:
        variants = await asyncio.to_thread(
            panels_pipeline.generate_panel_variants,
            panel, characters, art_style,
            _character_sheet_bytes, project_dir / "panels", 1, start,
        )
        if pr is None:  # 처음 생성에 실패했던 컷
            frames = panel.get("frames", [])
            pr = {"panel_number": body.panel_number,
                  "scene": frames[0].get("scene", "") if frames else panel.get("scene", ""),
                  "variants": [], "selected": 0}
            _panel_results.append(pr)
            _panel_results.sort(key=lambda p: p["panel_number"])
        pr["variants"].extend(variants)
        _persist_panels()

        return {"panel_number": body.panel_number,
                "new_variants": [_variant_view(v) for v in variants]}
    except Exception as e:
        raise HTTPException(500, f"컷 재생성 실패: {e}")


def _variant_view(v: dict) -> dict:
    p = Path(v["path"])
    try:
        rel = p.resolve().relative_to(OUTPUTS_DIR.resolve()).as_posix()
        return {"variant": v["variant"], "url": f"/outputs/{rel}?v={p.stat().st_mtime_ns}"}
    except (ValueError, OSError):
        return {"variant": v["variant"], "url": ""}


@app.get("/api/stage4/panels")
async def get_panels():
    if not _panel_results:
        return {"panels": []}
    by_num = {pr["panel_number"]: pr for pr in _panel_results}
    safe = []
    for panel in _all_panels(_current_story):
        pn = panel.get("panel_number")
        frames = panel.get("frames", [])
        scene = frames[0].get("scene", "") if frames else panel.get("scene", "")
        pr = by_num.get(pn)
        safe.append({
            "panel_number": pn,
            "scene": (pr or {}).get("scene") or scene,
            "variants": [_variant_view(v) for v in pr["variants"]] if pr else [],
            "selected": pr["selected"] if pr else 0,
        })
    return {"panels": safe}


# ── Stage 5: 페이지 배치 ──────────────────────────────────────────

@app.post("/api/stage5/layout")
async def generate_layout():
    global _layout_result
    if not _panel_results:
        raise HTTPException(400, "Stage 4 컷 이미지가 필요합니다.")

    canvas_width = _current_settings.get("canvas_width", 800)
    project_dir = OUTPUTS_DIR / "current"

    try:
        _layout_result = await asyncio.to_thread(
            layout_pipeline.layout_pages,
            _panel_results, _current_story, canvas_width,
            project_dir=project_dir,
        )
        return {
            "b64_preview": _layout_result["b64_preview"],
            "width": _layout_result["width"],
            "height": _layout_result["height"],
            "panel_count": len(_layout_result.get("panel_positions", [])),
        }
    except Exception as e:
        raise HTTPException(500, f"페이지 배치 실패: {e}")


@app.get("/api/stage5/layout")
async def get_layout():
    if not _layout_result:
        return {}
    return {
        "b64_preview": _layout_result.get("b64_preview", ""),
        "width": _layout_result.get("width", 0),
        "height": _layout_result.get("height", 0),
    }


# ── Stage 6: 말풍선 / 대사 합성 ──────────────────────────────────

@app.post("/api/stage6/bubbles")
async def generate_bubbles():
    global _bubble_result, _layout_result
    if not _layout_result and not _panel_results:
        raise HTTPException(400, "Stage 5 페이지 배치가 필요합니다.")

    cfg = config_store.load()
    font_path = cfg.get("font_path", "")
    project_dir = OUTPUTS_DIR / "current"

    try:
        if not _layout_result.get("panel_positions"):
            _layout_result = await asyncio.to_thread(
                layout_pipeline.layout_pages,
                _panel_results, _current_story,
                _current_settings.get("canvas_width", 800),
                project_dir=project_dir,
            )
        _bubble_result = await asyncio.to_thread(
            bubbles_pipeline.compose_bubbles,
            _layout_result["path"],
            _layout_result["panel_positions"],
            _current_story,
            font_path,
            project_dir,
        )
        return {
            "b64_preview": _bubble_result["b64_preview"],
            "width": _bubble_result["width"],
            "height": _bubble_result["height"],
        }
    except Exception as e:
        raise HTTPException(500, f"말풍선 합성 실패: {e}")


@app.get("/api/stage6/result")
async def get_bubble_result():
    if not _bubble_result:
        return {}
    return {
        "b64_preview": _bubble_result.get("b64_preview", ""),
        "width": _bubble_result.get("width", 0),
        "height": _bubble_result.get("height", 0),
    }


# ── Stage 7: 내보내기 ─────────────────────────────────────────────

def _existing_path(result: dict, fallback: str) -> str:
    """결과의 파일 경로. 서버 재시작으로 메모리가 비었으면 current 폴더의 파일을 쓴다."""
    p = (result or {}).get("path", "")
    if p and Path(p).exists():
        return p
    f = OUTPUTS_DIR / "current" / fallback
    return str(f) if f.exists() else ""


def _layout_path() -> str:
    return _existing_path(_layout_result, "pages/full_page.png")


def _bubble_path() -> str:
    return _existing_path(_bubble_result, "final/final_page.png")


def _final_page_path() -> str:
    return _bubble_path() or _layout_path()


@app.post("/api/stage7/export-png")
async def export_png():
    final_path = _final_page_path()
    if not final_path:
        raise HTTPException(400, "완성 페이지가 없습니다. 5·6단계(배치·말풍선)를 먼저 진행해 주세요.")
    project_dir = OUTPUTS_DIR / "current"
    try:
        panel_paths = await asyncio.to_thread(
            exporter.export_individual_panels, _panel_results, project_dir
        )
        return {
            "full_page": final_path,
            "panels": panel_paths,
            "panel_count": len(panel_paths),
        }
    except Exception as e:
        raise HTTPException(500, f"PNG 내보내기 실패: {e}")


@app.post("/api/stage7/export-pdf")
async def export_pdf():
    final_path = _final_page_path()
    if not final_path:
        raise HTTPException(400, "완성 페이지가 없습니다. 5·6단계(배치·말풍선)를 먼저 진행해 주세요.")
    project_dir = OUTPUTS_DIR / "current"
    try:
        pdf_path = await asyncio.to_thread(
            exporter.export_pdf, final_path, project_dir
        )
        return FileResponse(
            pdf_path, media_type="application/pdf",
            filename="webtoon.pdf",
        )
    except Exception as e:
        raise HTTPException(500, f"PDF 내보내기 실패: {e}")


@app.post("/api/stage7/export-zip")
async def export_zip():
    project_dir = OUTPUTS_DIR / "current"
    try:
        zip_path = await asyncio.to_thread(
            exporter.export_zip,
            _current_story, _panel_results, _character_sheets,
            _cover_result, {"path": _layout_path()}, {"path": _bubble_path()}, project_dir,
        )
        return FileResponse(
            zip_path, media_type="application/zip",
            filename=Path(zip_path).name,
        )
    except Exception as e:
        raise HTTPException(500, f"ZIP 내보내기 실패: {e}")


@app.get("/api/stage7/download/{filename:path}")
async def download_file(filename: str):
    file_path = OUTPUTS_DIR / "current" / "export" / filename
    if not file_path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    return FileResponse(str(file_path), filename=file_path.name)


# ── 프로젝트 저장 / 불러오기 ──────────────────────────────────────

class ProjectSaveRequest(BaseModel):
    name: str = ""


@app.post("/api/project/save")
async def save_project(body: ProjectSaveRequest):
    name = body.name or _current_story.get("title", "프로젝트")
    try:
        result = project_store.save_project(
            name, _current_settings, _current_story,
            _character_sheets, _cover_result, _panel_results,
            {"path": _layout_path()}, {"path": _bubble_path()},
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"프로젝트 저장 실패: {e}")


@app.get("/api/project/list")
async def list_projects():
    return {"projects": project_store.list_projects()}


@app.post("/api/project/load/{folder}")
async def load_project(folder: str):
    global _current_settings, _current_story, _character_sheets
    global _character_sheet_bytes, _panel_results, _cover_result
    global _layout_result, _bubble_result
    try:
        meta = project_store.load_project(folder)
        _current_settings = meta.get("settings", {})
        _current_story = meta.get("story", {})
        _character_sheets = meta.get("character_sheets", [])
        _character_sheet_bytes = {}
        for cs in _character_sheets:
            for v in cs.get("views", []):
                p = Path(v.get("path", ""))
                if p.exists():
                    _character_sheet_bytes[cs["id"]] = p.read_bytes()
                    break
        _panel_results = meta.get("panel_results", [])
        if not _panel_results:
            _load_panels()
        _persist_panels()
        _cover_result = {}
        cp = meta.get("cover_path", "")
        if cp and Path(cp).exists():
            import base64
            _cover_result = {"path": cp, "b64_preview": base64.b64encode(Path(cp).read_bytes()).decode()}
        _layout_result = {}
        lp = _existing_path({"path": meta.get("layout_path", "")}, "pages/full_page.png")
        if lp:
            import base64
            _layout_result = {"path": lp, "b64_preview": base64.b64encode(Path(lp).read_bytes()).decode()}
        _bubble_result = {}
        bp = _existing_path({"path": meta.get("bubble_path", "")}, "final/final_page.png")
        if bp:
            import base64
            _bubble_result = {"path": bp, "b64_preview": base64.b64encode(Path(bp).read_bytes()).decode()}
        return {"ok": True, "name": meta.get("name", folder)}
    except Exception as e:
        raise HTTPException(500, f"프로젝트 불러오기 실패: {e}")

