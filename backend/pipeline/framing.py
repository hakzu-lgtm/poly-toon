"""칸 모양에 맞춰 그림을 자를 때 인물 얼굴이 잘리지 않는 위치를 고른다.

얼굴 인식(OpenCV YuNet)이 가능하면 큰 얼굴(주로 주인공)이 칸 안에 들어오는 위치를,
얼굴을 못 찾으면(단순한 캐릭터 그림체 등) 위쪽을 더 남기는 위치를 고른다.
"""

from pathlib import Path

from PIL import Image

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "face_detection_yunet_2023mar.onnx"
SCORE_THRESHOLD = 0.6
MIN_FACE_RATIO = 0.03     # 그림 가로 대비 이보다 작은 얼굴(군중·오검출)은 무시
TOP_BIAS = 0.3            # 얼굴이 없을 때 세로로 자르는 기준 (0=위만 남김, 0.5=가운데)
GRID = 21                 # 후보 위치 수 (각 축)

try:
    import cv2
    import numpy as np
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:  # OpenCV가 없으면 얼굴 인식 없이 동작
    cv2 = None
    np = None


def detect_faces(img: Image.Image) -> list[tuple[float, float, float, float, float]]:
    """(x, y, w, h, 가중치) 목록. 가중치 = 면적 × 신뢰도 → 앞에 크게 나온 인물일수록 큼."""
    if cv2 is None or not MODEL_PATH.exists():
        return []
    try:
        arr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        h, w = arr.shape[:2]
        det = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (w, h), SCORE_THRESHOLD, 0.3, 50)
        _, faces = det.detect(arr)
    except Exception:
        return []
    out = []
    for f in [] if faces is None else faces:
        x, y, fw, fh, conf = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
        if fw < w * MIN_FACE_RATIO:
            continue
        # 머리카락·모자까지 살리도록 얼굴 상자를 위·옆으로 넓힌다
        x, y, fw, fh = x - fw * 0.15, y - fh * 0.35, fw * 1.3, fh * 1.45
        out.append((x, y, fw, fh, fw * fh * conf))
    return out


def _visible_fraction(mask_arr, box, ox, oy) -> float:
    """잘라낸 위치(ox, oy)에서 얼굴 상자가 칸 모양(mask) 안에 보이는 비율."""
    x, y, w, h = box
    mh, mw = mask_arr.shape
    xs = np.linspace(x, x + w, 5) - ox
    ys = np.linspace(y, y + h, 5) - oy
    gx, gy = np.meshgrid(xs, ys)
    inside = (gx >= 0) & (gx < mw) & (gy >= 0) & (gy < mh)
    vis = np.zeros_like(inside)
    vis[inside] = mask_arr[gy[inside].astype(int), gx[inside].astype(int)] > 0
    return float(vis.mean())


def fit_to_frame(img: Image.Image, mask: Image.Image) -> Image.Image:
    """mask(칸 모양, bbox 크기)를 꽉 채우도록 img를 비율 유지로 확대하고, 얼굴이 잘 보이는 위치를 잘라 낸다."""
    tw, th = mask.size
    img = img.convert("RGB")
    scale = max(tw / img.width, th / img.height)
    sw, sh = max(tw, round(img.width * scale)), max(th, round(img.height * scale))
    max_x, max_y = sw - tw, sh - th

    # 얼굴이 없을 때의 기본 위치: 가로는 가운데, 세로는 위쪽을 더 남김
    best = (max_x / 2, max_y * TOP_BIAS)

    faces = detect_faces(img) if (max_x or max_y or _slanted(mask)) else []
    if faces and np is not None:
        faces = [(x * scale, y * scale, w * scale, h * scale, wt) for x, y, w, h, wt in faces]
        mask_arr = np.array(mask)
        cands_x = np.linspace(0, max_x, GRID) if max_x else [0.0]
        cands_y = np.linspace(0, max_y, GRID) if max_y else [0.0]
        best_score = None
        for ox in cands_x:
            for oy in cands_y:
                score = sum(wt * _visible_fraction(mask_arr, (x, y, w, h), ox, oy)
                            for x, y, w, h, wt in faces)
                # 점수가 같으면 기본 위치에 가까운 쪽
                dist = abs(ox - max_x / 2) / (max_x or 1) + abs(oy - max_y * TOP_BIAS) / (max_y or 1)
                key = (round(score, 6), -dist)
                if best_score is None or key > best_score:
                    best_score, best = key, (ox, oy)

    # 원본에서 해당 영역만 잘라 확대 (전체를 먼저 확대하는 것보다 빠름)
    left, top = best[0] / scale, best[1] / scale
    return img.resize((tw, th), Image.LANCZOS,
                      box=(left, top, left + tw / scale, top + th / scale))


def _slanted(mask: Image.Image) -> bool:
    """칸이 사각형이 아니면(사선 칸) 상자 안에서도 가려지는 부분이 있다."""
    w, h = mask.size
    corners = [mask.getpixel((2, 2)), mask.getpixel((w - 3, 2)),
               mask.getpixel((2, h - 3)), mask.getpixel((w - 3, h - 3))]
    return min(corners) < 128
