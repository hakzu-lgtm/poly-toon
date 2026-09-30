"""FactChat 전용 네트워크 클라이언트.

★ 이 모듈이 프로젝트에서 유일한 외부 HTTP 호출 지점입니다.
설정된 FactChat base URL 이외의 호스트로는 절대 요청하지 않습니다.
"""

import base64
import io
import json
import re
from urllib.parse import urlparse

import httpx

from backend import usage_tracker

_TIMEOUT_TEXT = 120
_TIMEOUT_IMAGE = 300


class HostGuardError(Exception):
    pass


def _assert_host(url: str, allowed_host: str) -> None:
    target = urlparse(url).hostname
    allowed = urlparse(allowed_host.rstrip("/")).hostname
    if target != allowed:
        raise HostGuardError(
            f"차단: {target} 은(는) 허용된 호스트({allowed})가 아닙니다."
        )


# ── 텍스트 (OpenAI 호환 chat/completions) ──────────────────────

def chat(
    messages: list[dict],
    *,
    model: str,
    host: str,
    api_key: str,
    response_json: bool = False,
    max_tokens: int = 4096,
) -> str:
    url = f"{host.rstrip('/')}/v1/gateway/chat/completions"
    _assert_host(url, host)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    # response_format은 일부 게이트웨이에서 미지원 — 시스템 프롬프트로 JSON 강제

    r = httpx.post(url, headers=headers, json=body, timeout=_TIMEOUT_TEXT)
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage", {})
    usage_tracker.record_text(
        usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    )
    return data["choices"][0]["message"]["content"]


# ── 이미지 품질 프롬프트 ───────────────────────────────────────
# 실제 렌더링 품질/비용은 quality 파라미터가 결정한다.
# "8K", "ultra-detailed" 같은 과장 문구는 효과 없이 low 품질과 충돌하므로 두지 않는다.

QUALITY_PREFIX = "professional webtoon illustration, clean lineart, "

NEGATIVE_INSTRUCTION = (
    " Do NOT include any text, letters, words, watermarks, "
    "signatures, or logos in the image."
)

DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"

IMAGE_QUALITIES = ("low", "medium", "high")
DEFAULT_IMAGE_QUALITY = "medium"

# 편집 요청에 첨부하는 참조 이미지(캐릭터 시트)의 최대 변 길이.
# 참조 이미지는 입력 토큰으로 과금되므로 일관성 유지에 충분한 크기로 줄여 보낸다.
REF_IMAGE_MAX_SIDE = 512


def _enhance_prompt(prompt: str) -> str:
    return QUALITY_PREFIX + prompt + NEGATIVE_INSTRUCTION


def _resolve_quality(quality: str | None) -> str:
    if quality is None:
        from backend import config_store
        quality = config_store.load().get("image_quality", DEFAULT_IMAGE_QUALITY)
    return quality if quality in IMAGE_QUALITIES else DEFAULT_IMAGE_QUALITY


def _shrink_ref_image(img_bytes: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(img_bytes))
    if max(img.size) <= REF_IMAGE_MAX_SIDE:
        return img_bytes
    img.thumbnail((REF_IMAGE_MAX_SIDE, REF_IMAGE_MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ── 이미지 요청 공통 처리 ──────────────────────────────────────
# 재시도 정책 (크레딧 절약):
#  - 402(크레딧 부족): 즉시 CreditExhaustedError — 호출부는 전체 생성을 멈춘다.
#  - 5xx: 1회만 재시도. 게이트웨이가 실패 응답에도 과금할 수 있으므로 반복하지 않는다.
#  - 타임아웃: 재시도하지 않는다. 서버 쪽에서는 이미 생성·과금됐을 수 있다.
#  - 400이 quality 파라미터를 거부하면 quality 없이 1회 재시도한다.

class CreditExhaustedError(Exception):
    pass


def _error_detail(r: httpx.Response) -> str:
    try:
        detail = r.json().get("detail", r.text)
        if isinstance(detail, dict):
            return str(detail.get("message", detail))
        return str(detail)
    except ValueError:
        return r.text[:300]


def _post_image(kind: str, url: str, model: str, send) -> bytes:
    """send(drop_quality: bool) -> httpx.Response. 모든 시도를 호출 기록에 남긴다."""
    drop_quality = False
    server_retries = 1
    while True:
        try:
            r = send(drop_quality)
        except httpx.TimeoutException as e:
            usage_tracker.log_image_call(kind, model, "timeout")
            raise RuntimeError(f"이미지 생성 시간 초과({_TIMEOUT_IMAGE}초)") from e

        usage_tracker.log_image_call(kind, model, r.status_code)
        if r.status_code == 200:
            return base64.b64decode(r.json()["data"][0]["b64_json"])

        detail = _error_detail(r)
        if r.status_code == 402:
            raise CreditExhaustedError(f"FactChat 크레딧이 부족합니다: {detail}")
        if r.status_code == 400 and not drop_quality and "quality" in detail.lower():
            drop_quality = True
            continue
        if r.status_code >= 500 and server_retries > 0:
            server_retries -= 1
            continue
        raise RuntimeError(f"이미지 요청 실패 ({r.status_code}): {detail}")


# ── 이미지 생성 ────────────────────────────────────────────────

def generate_image(
    prompt: str,
    *,
    host: str,
    api_key: str,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = "1024x1024",
    quality: str | None = None,
) -> bytes:
    url = f"{host.rstrip('/')}/v1/api/openai/images/generate"
    _assert_host(url, host)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model, "prompt": _enhance_prompt(prompt), "size": size,
        "quality": _resolve_quality(quality), "n": 1,
    }

    def send(drop_quality: bool) -> httpx.Response:
        b = {k: v for k, v in body.items() if not (drop_quality and k == "quality")}
        return httpx.post(url, headers=headers, json=b, timeout=_TIMEOUT_IMAGE)

    img = _post_image("generate", url, model, send)
    usage_tracker.record_image()
    return img


# ── 이미지 편집 (캐릭터 일관성용, 참조 이미지 첨부) ──────────

def edit_image(
    images: list[bytes],
    prompt: str,
    *,
    host: str,
    api_key: str,
    model: str = DEFAULT_IMAGE_MODEL,
    size: str = "1024x1024",
    quality: str | None = None,
) -> bytes:
    url = f"{host.rstrip('/')}/v1/api/openai/images/edit"
    _assert_host(url, host)

    headers = {"Authorization": f"Bearer {api_key}"}
    images = [_shrink_ref_image(b) for b in images]

    data = {
        "model": model, "prompt": _enhance_prompt(prompt), "size": size,
        "quality": _resolve_quality(quality), "n": "1",
    }

    def send(drop_quality: bool) -> httpx.Response:
        d = {k: v for k, v in data.items() if not (drop_quality and k == "quality")}
        files = [("image", (f"ref_{i}.png", b, "image/png")) for i, b in enumerate(images)]
        return httpx.post(url, headers=headers, data=d, files=files, timeout=_TIMEOUT_IMAGE)

    img = _post_image("edit", url, model, send)
    usage_tracker.record_image_edit()
    return img


def use_reference_images() -> bool:
    """캐릭터 시트 참조(edit) 사용 여부. 편집 요청이 게이트웨이에서 계속 실패해 기본은 끔."""
    from backend import config_store
    return bool(config_store.load().get("use_reference_images", False))


# ── 연결 테스트 ────────────────────────────────────────────────

def list_models(host: str, api_key: str) -> list[str]:
    url = f"{host.rstrip('/')}/v1/gateway/models"
    _assert_host(url, host)
    r = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=_TIMEOUT_TEXT)
    r.raise_for_status()
    data = r.json()
    items = data.get("data", []) if isinstance(data, dict) else data
    return [i.get("id", "") for i in items if isinstance(i, dict)]


def test_connection(host: str, api_key: str, image_model: str = DEFAULT_IMAGE_MODEL) -> dict:
    """텍스트는 짧게 호출하고, 이미지는 크레딧이 드는 생성 대신 모델 목록으로 확인한다."""
    result = {"text": False, "image": False, "text_error": "", "image_error": ""}

    # 텍스트 테스트
    try:
        reply = chat(
            [{"role": "user", "content": "Say OK"}],
            model="claude-sonnet-5-5",
            host=host,
            api_key=api_key,
            max_tokens=10,
        )
        result["text"] = True
    except Exception as e:
        result["text_error"] = str(e)

    # 이미지 테스트 (모델 목록 조회 — 크레딧 차감 없음)
    try:
        result["image"] = image_model in list_models(host, api_key)
        if not result["image"]:
            result["image_error"] = f"게이트웨이에 {image_model} 모델이 없습니다."
    except Exception as e:
        result["image_error"] = str(e)

    return result


# ── JSON 안전 파싱 (LLM 응답에서 코드펜스 제거) ────────────────

def parse_json_response(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 잘린 JSON 복구 시도
    fixed = cleaned
    # 마지막 완전한 구조 지점 찾기
    for marker in ['"}', "},", "}]", "}\n"]:
        pos = fixed.rfind(marker)
        if pos > len(fixed) * 0.5:
            fixed = fixed[:pos + 1]
            break

    # 열린 문자열 닫기
    if fixed.count('"') % 2 != 0:
        fixed += '"'

    # 닫히지 않은 괄호 닫기
    open_brackets = fixed.count("[") - fixed.count("]")
    open_braces = fixed.count("{") - fixed.count("}")
    fixed += "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        # 최후 수단: 마지막 완전한 } 까지 자르고 다시 시도
        last_brace = fixed.rfind("}")
        if last_brace > 0:
            attempt = fixed[:last_brace + 1]
            ob = attempt.count("[") - attempt.count("]")
            attempt += "]" * max(ob, 0)
            ob2 = attempt.count("{") - attempt.count("}")
            attempt += "}" * max(ob2, 0)
            return json.loads(attempt)
        raise
