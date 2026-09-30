# 수정 내역 — 2026-08-25

## 1. FactChat 모델 ID 오류 수정 (텍스트 생성 404)

`claude-sonnet-4-6`, `gemini-3.1-flash-lite` 모델 ID가 더 이상 FactChat 게이트웨이에서 지원되지 않아
Stage 0 연결 테스트 및 스토리 생성 시 `404 Not Found` 오류가 발생했습니다.
`GET /v1/gateway/models`로 확인한 최신 모델 ID로 교체했습니다.

- `claude-sonnet-4-6` → `claude-sonnet-5`
- `gemini-3.1-flash-lite` → `gemini-3.5-flash-lite`

수정 파일:
- `config/config.json`
- `backend/config_store.py`
- `backend/factchat_client.py`
- `backend/pipeline/story.py`
- `backend/suggestions.py`

## 2. 새로고침 시 작업 내용이 초기화되는 문제 수정

서버(백엔드)에는 설정·스토리·캐릭터 시트·컷 이미지가 그대로 저장되어 있었지만,
프론트엔드가 페이지 로드 시 이를 다시 불러와 화면에 채우는 로직이 없어서
새로고침하면 화면만 빈 상태로 보이는 문제였습니다.

`frontend/app.js`에 `restoreState()` 함수를 추가해 페이지 로드 시 아래를 순서대로 복원합니다:
- Stage 1: 저장된 웹툰 설정 (키워드/장르/그림체/장 구성 등)
- Stage 2: 생성된 스토리 (시놉시스/등장인물/컷별 시나리오)
- Stage 3: 캐릭터 시트 카드 + 표지 이미지
- Stage 4: 컷 이미지 갤러리 (후보 이미지 포함)

## 3. "AI가 시나리오를 작성 중입니다..." 로딩 메시지가 안 사라지는 문제 수정

`frontend/style2.css`에 범용 `.hidden` 클래스 규칙이 정의돼 있지 않아서
(`.stage.hidden`처럼 특정 조합에서만 정의됨), JS가 로딩 스피너나 버튼에 `hidden` 클래스를
추가해도 실제 화면에서 사라지지 않는 문제였습니다.

```css
.hidden { display: none !important; }
```

전역 규칙을 추가해 로딩 스피너·버튼 등 `hidden` 클래스를 사용하는 모든 요소가
정상적으로 표시/숨김 처리되도록 수정했습니다.

또한 `style2.css`에 캐시 무효화용 버전 파라미터(`?v=7`)가 없어 브라우저가 예전 CSS를
계속 사용하던 문제도 함께 수정했습니다 (`index.html`).

## 4. 컷 이미지 갤러리 3열 레이아웃으로 변경

기존에는 컷 이미지가 1개씩 세로로 나열되어 여러 컷을 한눈에 비교하기 어려웠습니다.
`frontend/style2.css`의 `.panels-gallery`를 세로 flex 목록에서 **3열 grid**로 변경해
컷 1·2·3이 한 줄에, 4·5·6이 다음 줄에 표시되도록 했습니다.

반응형 처리도 추가:
- 화면 폭 1100px 이하 → 2열
- 화면 폭 640px 이하 → 1열

## 변경 파일 목록

- `config/config.json`
- `backend/config_store.py`
- `backend/factchat_client.py`
- `backend/pipeline/story.py`
- `backend/suggestions.py`
- `frontend/app.js`
- `frontend/style2.css`
- `frontend/index.html`
