# BUILD_PROMPT.md — 웹툰 자동 생성 로컬 웹프로그램 (FactChat 전용)

> 이 문서는 **Claude Code가 그대로 읽고 빌드**하기 위한 사양서입니다.
> 한 번에 전부 만들지 말고 **아래 "빌드 순서"의 단계별로** 작업하고, **각 단계가 끝날 때마다 "다음에 추가하면 좋을 내용 3가지"를 사용자에게 제안**한 뒤 다음 단계로 넘어가세요.

---

## 0. 프로젝트 개요

- **이름**: `webtoon-maker` (가칭)
- **목표**: 사용자가 핵심 키워드·그림체만 입력하면, 스토리 → 캐릭터 시트 → 컷 이미지 → 페이지 배치 → 한글 말풍선 → PNG/PDF/ZIP 내보내기까지 **완전 자동**으로 진행되는 **로컬 웹프로그램**.
- **실행 환경**: 사용자 Windows PC(예: i9 / RTX 4070 Super / 64GB). 브라우저에서 `http://localhost`로 접속해 사용.
- **대상 사용자**: **한국폴리텍대학 교직원**. 디지털 도구에 익숙한 실무자 → UI는 **세련되고 밝고 전문적**으로. 과한 친절·큰 버튼 위주의 "초보자 톤"은 지양하고, 깔끔한 업무용 SaaS 느낌으로.
- **핵심 목적**: 교직원이 홍보·교육·행사용 웹툰 콘텐츠를 빠르게 자체 제작.

---

## 1. 절대 지켜야 할 제약 (HARD CONSTRAINTS)

1. **외부 API 절대 금지.** OpenAI·Google·Anthropic 등 **외부 클라우드를 직접 호출하지 않는다.** 모든 AI 호출(텍스트·이미지)은 **오직 FactChat / kopo.factchat.bot 내부 게이트웨이**로만 나간다.
   - 네트워크 호출이 일어나는 코드는 **반드시 단일 모듈(`backend/factchat_client.py`)에만** 존재한다.
   - 그 모듈은 **설정된 FactChat base URL 외 어떤 도메인에도 요청하지 않는다.** (다른 호스트로 가는 요청은 코드에서 막을 것 — assertion/가드 추가.)
2. **로컬 전용.** 외부 서버에 데이터를 올리지 않는다. 생성물·설정은 사용자 PC 안에만 저장한다.
3. **API 키는 사용자가 입력**하고, **사용자 PC에 로컬 저장**한다. 키를 소스코드·git·로그에 절대 남기지 않는다.
4. **한글 깨짐 방지.** 말풍선 대사 텍스트는 **이미지 생성 모델에게 그리게 하지 말 것.** 이미지에는 그림만 생성하고, **한글 대사는 프로그램이 후처리로 합성**한다(맑은 고딕).

---

## 2. 기술 스택

- **백엔드**: Python 3.11+ / **FastAPI** + uvicorn
  - 이미지 합성: **Pillow(PIL)** (말풍선·텍스트·페이지 배치)
  - PDF: Pillow 또는 `img2pdf`
  - ZIP: 표준 `zipfile`
  - HTTP: `httpx` (FactChat 호출)
- **프런트엔드**: **빌드 없는 정적 HTML/CSS/JS** (FastAPI가 `/`에서 서빙). Node 빌드 단계가 없어 교직원 PC에서 `start.bat` 더블클릭만으로 바로 뜬다. 인터랙션은 **바닐라 JS + 약간의 Alpine.js**. 단, CSS는 공들여 **세련된 업무용 톤**으로 만든다(섹션 10).
- **실행 런처**: Windows용 `start.bat` (가상환경 생성 → 의존성 설치 → uvicorn 실행 → 기본 브라우저 자동 오픈).
- **저장소**: 로컬 파일(`config/config.json`, `outputs/<프로젝트명>/...`).

---

## 3. 디렉터리 구조

```
webtoon-maker/
├─ start.bat                  # 더블클릭 실행 (Windows)
├─ requirements.txt
├─ README.md                  # 교직원용 간결 사용설명서(한국어, 스크린샷 자리표시)
├─ .gitignore                 # config/ outputs/ .venv/ 제외
├─ backend/
│  ├─ main.py                 # FastAPI 앱 / 라우팅 / 정적 서빙
│  ├─ factchat_client.py      # ★ 유일한 네트워크 호출 지점 (FactChat 전용)
│  ├─ config_store.py         # API 키/설정 로컬 저장·로드
│  ├─ pipeline/
│  │  ├─ story.py             # 스토리·시나리오·컷/대사 생성 (LLM)
│  │  ├─ character.py         # 캐릭터 시트 자동 생성 (이미지)
│  │  ├─ panels.py            # 컷별 이미지 생성 (캐릭터 일관성)
│  │  ├─ layout.py            # 세로 스크롤 페이지 배치
│  │  ├─ bubbles.py           # 말풍선 + 한글 대사 합성
│  │  └─ exporter.py          # PNG / PDF / ZIP 내보내기
│  └─ suggestions.py          # ★ "매 단계 3가지 추천" 생성 (LLM)
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  ├─ style.css
│  └─ assets/                 # 브랜딩 에셋 (함께 제공됨)
│     ├─ logo_chungju.png     # 충주캠퍼스 로고 (상단 헤더)
│     ├─ favicon.png          # 64×64 쿼드콥터 파비콘
│     ├─ favicon.ico          # 16/32/48/64 멀티사이즈
│     └─ favicon.svg          # 벡터 원본(확대용)
├─ config/                    # (git 제외) config.json 저장 위치
└─ outputs/                   # (git 제외) 생성 결과물
```

---

## 4. FactChat API 연동 명세

> ✅ **아래 값은 KOPO 인스턴스에서 curl로 라이브 검증 완료(2026-06-19).** 텍스트·이미지 생성 모두 실제 호출 성공.

### 4.1 기본 정보 (라이브 검증 완료)

- **공통 base 호스트**: `https://factchat-cloud.mindlogic.ai`
- **텍스트(게이트웨이, OpenAI 호환)**: `POST .../v1/gateway/chat/completions` — ✅ 검증됨
- **이미지 생성**: `POST .../v1/api/openai/images/generate` — ✅ 검증됨(**`gpt-image-2`, base64 반환**)
- **이미지 편집(캐릭터 일관성 핵심)**: `POST .../v1/api/openai/images/edit` — `gpt-image-2`, **참조 이미지 최대 16장 입력**(문서 기준)
- **인증 헤더**: `Authorization: Bearer <API_KEY>` — ✅ 검증됨 (대안: `x-api-key: <API_KEY>`)
- **단일 키로 텍스트·이미지 모두 호출**, 사용량은 키 발급 계정의 크레딧에서 차감.

**단계별 사용 모델 (효율적 분배 — 검증된 모델 목록 기준):**

| 용도 | 모델 ID | 비고 |
| --- | --- | --- |
| 스토리·시나리오·등장인물 설정 | `claude-opus-4-8` | 최신 Opus, 창작·일관성 |
| 컷 분할·컷별 이미지 프롬프트 | `claude-sonnet-4-6` | 구조화 작업 |
| 매 단계 "3가지 추천" | `gemini-3.1-flash-lite` (또는 `claude-haiku-4-5`) | 가장 저렴한 보조 |
| 이미지 생성/편집 | `gpt-image-2` | ✅ 검증됨 |

> 모델 ID는 **`GET {host}/v1/gateway/models`** 로 언제든 최신 목록을 받을 수 있다(이미지 모델은 이 목록에 안 나오고, 이미지 엔드포인트에 ID를 직접 전달).

> ⚠️ **주의: 텍스트와 이미지의 base 경로가 다르다.** 텍스트는 `/v1/gateway/...`, 이미지는 `/v1/api/openai/...`. 게이트웨이(`/v1/gateway/images/...`)에는 이미지 경로가 **없어서 404**가 난다. `config`에는 호스트(`https://factchat-cloud.mindlogic.ai`)만 저장하고, 각 기능별 경로는 코드에서 조합한다.

> base 호스트는 **설정값(config)** 으로 받는다. 다른 기관(온프레미스 등)은 도메인이 다를 수 있으므로 키 입력 시 호스트도 함께 받게 하되, 기본값은 위 호스트.

### 4.2 텍스트(스토리·추천) 호출 — OpenAI 호환 방식

```python
# factchat_client.py (검증된 호출 형식)
import httpx

FACTCHAT_HOST = "https://factchat-cloud.mindlogic.ai"  # config에서 주입

def chat(messages, model, host, api_key, response_json=False):
    url = f"{host.rstrip('/')}/v1/gateway/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "messages": messages, "max_tokens": 4096}
    if response_json:
        body["response_format"] = {"type": "json_object"}  # 지원 시
    r = httpx.post(url, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]  # ✅ 검증된 응답 형식
```

- **단계별 텍스트 모델**(섹션 4.1 표): 스토리=`claude-opus-4-8`, 컷 프롬프트=`claude-sonnet-4-6`, 추천=`gemini-3.1-flash-lite`. 각 단계가 `chat()`에 다른 `model`을 넘긴다.
- 스토리 구조화 출력은 **JSON으로만 응답**하도록 시스템 프롬프트에서 강하게 지시하고, 코드에서 안전 파싱(코드펜스 제거 후 `json.loads`).

### 4.3 이미지 호출 (라이브 검증 완료)

- **생성**: `POST {host}/v1/api/openai/images/generate`, 모델 **`gpt-image-2`**. 파라미터: `prompt`(필수), `model`, `size`(`1024x1024`/`1536x1024`/`1024x1536`/`auto`), `n`. **응답은 `data[0].b64_json`(base64)** — ✅ 검증됨.
- **편집(캐릭터 일관성)**: `POST {host}/v1/api/openai/images/edit`, 모델 `gpt-image-2`. `image`(편집할 이미지 또는 배열, **최대 16장**), `prompt`(필수), `size`, `n`, 선택적 `mask`. → **캐릭터 시트를 참조로 넣어 컷 일관성 유지**.

```python
def generate_image(prompt, host, api_key, model="gpt-image-2", size="1024x1024"):
    url = f"{host.rstrip('/')}/v1/api/openai/images/generate"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "prompt": prompt, "size": size, "n": 1}
    r = httpx.post(url, headers=headers, json=body, timeout=300)
    r.raise_for_status()
    import base64
    return base64.b64decode(r.json()["data"][0]["b64_json"])  # PNG bytes
```

> **이미지 모델 선택 정리 (테스트로 확정):**
> - ✅ **`gpt-image-2`** — 기본값. 위 `/v1/api/openai/images/generate`·`/images/edit`로 동작 확인.
> - **Google `/v1/api/google/models/generate-images`** 는 **Imagen 전용**(`imagen-3.0-generate-002`, `imagen-3.0-capability-001`). `{model, prompt}` 형식.
> - **Nano Banana(Gemini 이미지)** 는 위 경로로 **불가**(`400 FAILED_PRECONDITION: Gemini cannot be accessed through Vertex Predict/RawPredict API`). 쓰려면 **`/v1/api/google/models/generate-content`** 에 Gemini 멀티모달 형식(`contents` + `generationConfig.responseModalities: ["TEXT","IMAGE"]`)으로 호출해야 하고, 모델 ID는 **`gemini-3.1-flash-image-preview`**(Nano Banana 2) / `gemini-3-pro-image-preview`(Pro) / `gemini-2.5-flash-image`. 응답은 `candidates[0].content.parts[].inlineData.data`(base64).
> - **권장: 기본은 `gpt-image-2`로 충분**(생성+편집·참조 16장). 한글 대사는 어차피 Pillow 합성이라 Nano Banana의 텍스트 강점은 불필요. Nano Banana는 빌드 후 여유 있을 때 generate-content 경로로 실험.

### 4.4 가드(외부 호출 차단)

`factchat_client.py`는 요청 직전 URL 호스트가 **설정된 FactChat base URL의 호스트와 일치하는지 검사**하고, 불일치 시 예외를 던진다. 다른 모듈에서는 `httpx`/`requests`를 직접 import 금지(린트 규칙 또는 코드리뷰 메모로 명시).

---

## 5. 프로그램 단계 (Stage) — 런타임 흐름

프런트는 **세로 스텝 진행 UI**(현재 단계 강조, 이전/다음 버튼). **각 Stage가 끝나면 백엔드 `suggestions.py`가 LLM으로 "추가하면 좋을 내용 3가지"를 생성**해 카드 3개로 보여준다(섹션 6).

| Stage | 이름 | 입력 | 처리 | 출력 |
|---|---|---|---|---|
| 0 | **설정/연결** | API 키, base URL, 모델 선택 | 로컬 저장 + 연결 테스트 호출 | "연결 성공" 표시 |
| 1 | **웹툰 설정** | 핵심 키워드, 장르, 분위기, **그림체**, 컷 수, 화면 비율, 등장인물 수, 대사 톤 | 입력 검증 | 설정 객체 |
| 2 | **스토리 생성** | (Stage1 결과) | LLM 호출 → 시놉시스 + 등장인물 설정(외모·의상·성격 고정 묘사) + **컷별 장면묘사 + 대사** JSON | 시나리오 JSON(편집 가능) |
| 3 | **캐릭터 시트** | 등장인물 설정 | 인물별 레퍼런스 이미지 생성(정면/기본 표정, 동일 그림체) | 캐릭터 시트 PNG들 |
| 4 | **컷 이미지** | 컷별 장면 + 캐릭터 시트 | **캐릭터 시트를 레퍼런스로** 컷마다 이미지 생성(일관성 유지). 컷당 2~3안 생성 후 택1 옵션 | 컷 이미지 PNG들 |
| 5 | **페이지 배치** | 컷 이미지들 | **세로 스크롤 웹툰 레이아웃**으로 배치(컷 간 여백·구분선) | 페이지 이미지 |
| 6 | **말풍선/대사** | 컷별 대사 + 페이지 | Pillow로 **맑은 고딕 한글 말풍선 합성**(자동 줄바꿈, 화자별 위치) | 완성 페이지 |
| 7 | **내보내기** | 완성 페이지 | PNG(긴 한 장 / 컷별) · PDF · ZIP 패키징 | 다운로드 |

각 Stage는 독립 실행·재실행 가능(이전 단계 결과 캐시). 사용자가 Stage 2 시나리오나 Stage 4 컷을 **수정 후 부분 재생성**할 수 있어야 한다.

---

## 6. ★ "매 단계 3가지 추천" 기능 (필수 핵심)

- 각 Stage 완료 직후, `suggestions.py`가 현재 맥락(현재 단계, 지금까지 만든 결과 요약, 사용자 설정)을 LLM에 전달해 **정확히 3개의 짧은 제안**을 받는다.
- LLM 출력은 **JSON 배열 3개**로 강제:
  ```json
  [
    {"title": "감정 강조 컷 추가", "desc": "...", "action": "add_emotion_panel"},
    {"title": "배경 디테일 보강", "desc": "...", "action": "enrich_background"},
    {"title": "반전 대사 삽입",  "desc": "...", "action": "add_twist_line"}
  ]
  ```
- 프런트는 카드 3개로 표시. **클릭하면 해당 제안이 실제로 적용/추가**되도록(가능한 항목은 자동 반영, 어려운 항목은 해당 입력칸으로 안내).
- 추천은 **그 단계 맥락에 맞아야** 한다(예: Stage 2에선 스토리 관련, Stage 5에선 레이아웃 관련).

---

## 7. 캐릭터 일관성 전략 (가장 어려운 부분 — 신경 써서)

1. Stage 3에서 **캐릭터별 시트**를 먼저 만들어 "외모 고정 기준"을 확보한다.
2. Stage 4 컷 생성 시 **항상 해당 인물의 캐릭터 시트를 레퍼런스 이미지로 첨부**하고, 프롬프트에 "이 인물의 외모/의상/헤어를 유지" 명시.
3. **그림체 묘사 문자열을 전 컷에 동일하게 주입**(예: "soft cel-shaded webtoon style, clean lineart, pastel palette").
4. Nano Banana 계열의 **다중 이미지 입력**으로 다인물 장면은 여러 캐릭터 시트를 함께 전달.
5. 그래도 흔들릴 수 있으므로 **컷당 2~3안 생성 → 사용자 택1** UI를 둔다.
6. (선택) 동일 seed/스타일 파라미터 지원 시 고정.

---

## 8. 말풍선 / 한글 대사 명세

- **폰트**: Windows 기본 **맑은 고딕** `C:\Windows\Fonts\malgun.ttf` (없을 경우 대비해 폰트 경로 설정값 + 번들 폰트 fallback).
- Pillow `ImageDraw`로: 흰색 둥근 말풍선 + 꼬리, **자동 줄바꿈**(글자 폭 계산), 화자에 따라 위치(상/좌/우).
- 대사 길이에 따라 말풍선 크기 자동. 나레이션 박스(사각)와 대사 말풍선(둥근) 구분.
- **이미지 모델에 텍스트를 절대 그리게 하지 않는다.** 그림 위에 코드로 합성.

---

## 9. 페이지 배치 & 내보내기

- **세로 스크롤(웹툰 표준)**: 컷을 위→아래로 쌓고 컷 간 일정 여백.
- 화면 비율은 Stage 1 설정(예: 가로 800px 고정, 세로 가변).
- 내보내기 3종:
  - **PNG**: ① 한 편 전체 긴 한 장 ② 컷별 개별 PNG (옵션)
  - **PDF**: 페이지 단위
  - **ZIP**: 시나리오 JSON + 캐릭터 시트 + 컷 PNG + 완성 페이지 + PDF 묶음
- 결과물은 `outputs/<프로젝트명_날짜>/`에 저장하고 브라우저에서 다운로드 링크 제공.

---

## 10. UI / 디자인 & 브랜딩

> 대상은 **폴리텍대학 교직원**(실무자). 톤은 **세련·밝음·전문** — 깔끔한 업무용 SaaS 느낌. 어린이용·초보자용 과장된 톤 금지.

### 10.1 브랜딩
- **상단 헤더(고정)**: 좌측에 **충주캠퍼스 로고**(`frontend/assets/logo_chungju.png`) + 앱 타이틀(예: "웹툰 메이커"), 우측에 API 키 연결 상태 배지 + 설정 버튼. 로고는 **원본 비율 유지**, 변형·왜곡 금지, 좌우 충분한 여백.
- **파비콘**: `frontend/assets/favicon.png`(64×64, 쿼드콥터) + `favicon.ico`(멀티사이즈). `index.html`에 링크:
  ```html
  <link rel="icon" type="image/png" sizes="64x64" href="/assets/favicon.png">
  <link rel="icon" href="/assets/favicon.ico">
  ```
- 탭 타이틀에도 앱 이름 노출.

### 10.2 디자인 토큰
- **베이스**: 라이트 테마. 배경 `#F7F9FC`(연그레이), 카드 `#FFFFFF`, 텍스트 `#1B2330`/보조 `#64748B`.
- **메인 컬러**: 로고·파비콘과 통일된 **블루~시안** — primary `#2563EB`, accent `#19C9D6`, 그라데이션 `#3B82F6 → #19D3C5`(헤더 바/주요 버튼 포인트).
- **타이포**: 한글 친화 산세리프 **Pretendard**(웹폰트 동봉 또는 CDN, 없으면 시스템 `Malgun Gothic`/`-apple-system` fallback).
- **형태**: 라운드 코너 12~16px, 부드러운 그림자(`0 4px 20px rgba(20,40,80,.08)`), 넉넉한 여백, 1px 연한 보더.

### 10.3 레이아웃
- 상단 고정 헤더(로고+상태) → 그 아래 **진행 스텝 인디케이터**(Stage 0~7, 현재 단계 강조) → 메인 작업 영역(좌: 입력/설정, 우: 결과 프리뷰) → 하단/사이드에 **3가지 추천 카드**.
- 데스크톱 우선(교직원 PC). 버튼·상태·로딩은 명확하되 과하지 않게. 로딩 시 스켈레톤/스피너 + 진행 문구.
- 접근성: 충분한 명도 대비, 키보드 포커스 표시.

---

## 11. API 키 저장 & 보안

- Stage 0에서 입력받아 `config/config.json`에 저장:
  ```json
  {
    "host": "https://factchat-cloud.mindlogic.ai",
    "api_key": "...",
    "models": {
      "story": "claude-opus-4-8",
      "panel_prompt": "claude-sonnet-4-6",
      "suggestions": "gemini-3.1-flash-lite",
      "image": "gpt-image-2"
    },
    "font_path": "C:\\Windows\\Fonts\\malgun.ttf"
  }
  ```
- 저장 위치는 **앱 폴더 내 `config/`** (사용자 PC 로컬). `.gitignore`에 포함.
- 키는 **로그·콘솔·에러 메시지에 출력 금지**(마스킹: 앞 4자리만 표기).
- 재실행 시 자동 로드, "키 변경" 버튼 제공.
- (선택) 간단 난독화 저장(예: base64) — 단, 보안 자랑 금지. 로컬 단일 사용자 가정.

---

## 12. 검증 상태 / 남은 확인 항목

**라이브 검증 완료(2026-06-19, KOPO 키로 curl 테스트):**
- ✅ 호스트 `https://factchat-cloud.mindlogic.ai`, 인증 `Authorization: Bearer`
- ✅ 텍스트 `/v1/gateway/chat/completions` + `claude-opus-4-8`/`claude-sonnet-4-6` 등 (모델 목록 `GET /v1/gateway/models`로 확인)
- ✅ 이미지 생성 `/v1/api/openai/images/generate` + **`gpt-image-2`** (응답 base64)
- ✅ 이 조직 키에 이미지 생성 권한 열려 있음
- ℹ️ Google 이미지: `generate-images`는 **Imagen 전용**, Nano Banana(Gemini)는 `generate-content` 멀티모달 경로 필요 — 섹션 4.3 참조

**빌드 중 추가 확인(선택):**
1. **이미지 편집** `/v1/api/openai/images/edit` + `gpt-image-2` 실제 동작(캐릭터 일관성용) — 빌드 초기 1회 테스트 권장.
2. **맑은 고딕 폰트 경로**(`C:\Windows\Fonts\malgun.ttf`) 존재 확인 + 없을 때 fallback.
3. (원하면) **Nano Banana 2** `gemini-3.1-flash-image-preview` via `generate-content` 실험 — 필수 아님.

---

## 13. 빌드 순서 (Claude Code 작업 지침)

아래 순서로 **점진적으로** 만들고, **각 단계 종료 시 "다음에 추가하면 좋을 3가지"를 사용자에게 제안**한 뒤 진행한다.

1. 프로젝트 골격 + `start.bat` + FastAPI "Hello" + 정적 프런트 서빙. **이때 디자인 토큰(섹션 10)·상단 로고 헤더·파비콘을 먼저 적용**해 이후 모든 화면이 일관된 톤으로 쌓이게 한다.
2. **`factchat_client.py` + Stage 0(키 입력·저장·연결 테스트)** → 실제 텍스트 호출 1회 성공시키기. **여기서 이미지 호출도 1회 테스트**해 스키마 확정.
3. Stage 1(설정 입력 UI) + Stage 2(스토리 JSON 생성·표시·편집).
4. `suggestions.py` + **3가지 추천 카드 컴포넌트**(이후 모든 Stage에 연결).
5. Stage 3(캐릭터 시트) → Stage 4(컷 이미지, 일관성·2~3안 택1).
6. Stage 5(세로 배치) → Stage 6(말풍선/한글 합성).
7. Stage 7(PNG/PDF/ZIP 내보내기).
8. README(교직원용) + 전체 흐름 점검 + 에러 처리/로딩 표시.

---

## 14. 완료 기준 (Definition of Done)

- [ ] 외부 API 호출이 **전혀 없고**, 모든 AI 호출이 설정된 FactChat base URL로만 나간다(가드 동작 확인).
- [ ] 키만 입력하면 `start.bat` 더블클릭 → 브라우저에서 끝까지 진행 가능.
- [ ] 키워드·그림체 입력만으로 스토리→캐릭터→컷→배치→말풍선→내보내기 자동 완주.
- [ ] **모든 Stage 종료 시 3가지 추천**이 맥락에 맞게 표시되고, 클릭 시 반영된다.
- [ ] 캐릭터가 컷 전반에서 **일관**되게 보인다(시트 레퍼런스 적용 확인).
- [ ] 한글 대사가 **깨지지 않고** 말풍선에 합성된다.
- [ ] PNG·PDF·ZIP 다운로드가 정상 동작한다.
- [ ] API 키가 git·로그·화면에 노출되지 않는다.
- [ ] 상단 헤더에 **충주캠퍼스 로고**가 비율 유지로 표시되고, 탭에 **쿼드콥터 파비콘**이 뜬다.
- [ ] UI가 **세련·밝은 업무용 톤**(라이트 테마, 블루~시안 포인트)으로 일관되게 적용된다.
