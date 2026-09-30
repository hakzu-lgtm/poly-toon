import json
import sys
import time
import traceback

sys.path.insert(0, ".")

from pathlib import Path
from backend.pipeline import panels as panels_pipeline

story = json.loads(open("outputs/current/_story.json", encoding="utf-8").read())
settings = json.loads(open("outputs/current/_settings.json", encoding="utf-8").read())

characters = story.get("characters", [])
panel = None
for ch in story.get("chapters", []):
    for p in ch.get("panels", []):
        if p.get("panel_number") == 1:
            panel = p
            break
    if panel:
        break

print("panel keys:", list(panel.keys()) if panel else None)
print("frames:", len(panel.get("frames", [])) if panel else 0)
print("characters_in_scene:", panel.get("characters_in_scene") if panel else None)

char_sheets = {}
chars_dir = Path("outputs/current/characters")
for f in chars_dir.glob("*_sheet.png"):
    cid = f.stem.replace("_sheet", "")
    char_sheets[cid] = f.read_bytes()
print("char_sheets loaded:", list(char_sheets.keys()))

art_style = settings.get("art_style", "webtoon style")

t0 = time.time()
try:
    variants = panels_pipeline.generate_panel_variants(
        panel, characters, art_style, char_sheets,
        Path("outputs/current/panels"), 1,
    )
    print("SUCCESS in", round(time.time() - t0, 1), "s")
    print([v["path"] for v in variants])
except Exception:
    print("FAILED after", round(time.time() - t0, 1), "s")
    traceback.print_exc()
