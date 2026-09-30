# 수정 내역 — 2026-09-30

주제: **크레딧 사용량 절감**, 최신 모델 적용, 생성 실패 처리 개선

## 배경

- FactChat 크레딧은 **월 3,000**이고 매월 1일에 충전된다 (다음 충전: 2026-10-01 00:00).
- 이미지 한 장 차감량: `gpt-image-2`는 **46**, `gpt-image-2.5-sunburst`/`gpt-image-2.5-flare`는 **15** (사용자 확인).
- 9/30에 이미지 약 10장을 만들고 크레딧 3,000이 모두 소진됐다. 컷 생성 도중 `402`(크레딧 부족)가 발생해
  컷 6~12가 **회색 빈 이미지**로 저장됐다 (`outputs/current/panels/panel_06~12_v0.png`, 각 약 8KB).

### 원인 분석 (추정 포함)

- 스토리 생성은 원인이 아니다. 이날은 스토리를 새로 만들지 않았고, 텍스트 호출은 6회, 약 1,200토큰뿐이었다.
- 성공한 이미지는 12장(약 552크레딧)이다. 나머지 약 2,450크레딧은 **실패한 요청**으로 추정한다.
  - 캐릭터 시트를 참조로 첨부하는 편집 요청(`/images/edit`)은 **8월, 9월 모두 성공 0건**이다. 항상 `500`을 반환했다.
  - 기존 코드는 칸마다 편집 요청을 최대 3회 시도한 뒤 참조 없는 생성을 1회 더 했다. 칸 하나당 최대 4회 호출이다.
  - 실패한 요청도 게이트웨이가 과금했다면 숫자가 대략 맞는다. **FactChat 대시보드에서 요청별 차감 내역으로 확인이 필요하다.**
- 결과적으로 캐릭터 참조가 한 번도 적용되지 않았다. 컷마다 캐릭터 외형이 달라질 수 있다.

## 1. 모델 변경

`GET /v1/gateway/models`로 게이트웨이 지원 여부를 확인한 뒤 교체했다.

| 용도 | 이전 | 변경 |
|---|---|---|
| 스토리 (`story`) | `claude-opus-4-8` | `claude-opus-5-5` |
| 컷 프롬프트 (`panel_prompt`) | `claude-sonnet-5` | `claude-sonnet-5-5` |
| 추천 (`suggestions`) | `gemini-3.5-flash-lite` | 유지 |
| 이미지 (`image`) | `gpt-image-2` | `gpt-image-2.5-sunburst` |

- `gpt-image-2.5-sunburst`는 **아직 실제 생성 테스트를 하지 못했다** (크레딧 소진).
- `flare`와의 차이는 알 수 없어 sunburst를 임의로 골랐다. 설정 화면의 이미지 모델 칸에서 바꿀 수 있다.
- 코드 곳곳에 있던 기본값 `"gpt-image-2"`를 `factchat_client.DEFAULT_IMAGE_MODEL` 하나로 통일했다.

## 2. 이미지 요청 파라미터와 프롬프트

- `quality` 파라미터(`low`/`medium`/`high`, 기본 `medium`)를 추가했다. 설정 화면의 "이미지 품질"에서 고른다.
  - 게이트웨이가 `quality`를 거부(400)하면 이 파라미터를 빼고 1회 재시도한다.
  - 크레딧이 장 단위로 차감된다면 품질을 낮춰도 절약되지 않을 수 있다. 차감량 비교가 필요하다.
- 참조 이미지(캐릭터 시트)는 전송 전에 긴 변 512px로 축소한다 (`REF_IMAGE_MAX_SIDE`).
- 프롬프트에서 `masterpiece`, `ultra-detailed`, `8K resolution` 같은 과장 문구를 제거했다.

## 3. 크레딧 절감 조치

- **패널당 최대 칸 수**(`max_frames_per_panel`, 기본 2)를 추가했다. 칸 하나가 이미지 한 장이다.
  - 스토리 프롬프트가 "2~4칸" 대신 "N칸 이하"로 작성하게 했다.
  - 기존 스토리도 생성 시점에 칸 수를 자르고 칸 수에 맞는 레이아웃으로 바꾼다 (`panels._fit_layout`).
  - `1-full`, `2-col` 레이아웃을 추가했다. `2-col`은 원래 정의가 없어 항상 `2-row`로 처리되던 버그였다.
- **캐릭터 시트 참조**(`use_reference_images`)는 기본 **끔**이다. 편집 요청이 계속 실패하기 때문이다.
  켜 둔 상태에서 실패하면 참조 없이 1회만 생성한다.
- **재시도 규칙**(`factchat_client._post_image`):
  - `402` 크레딧 부족: `CreditExhaustedError`를 발생시키고 캐릭터·컷 생성 스트림을 **즉시 중단**한다.
  - `5xx`: 1회만 재시도한다.
  - 타임아웃: 재시도하지 않는다. 서버에서는 이미 생성됐을 수 있다.
  - 그 밖의 실패: 회색 빈 이미지로 숨기지 않고 오류를 표시한다.
- 표지 생성에서 실패 시 같은 생성을 한 번 더 하던 중복 호출을 제거했다.
- **연결 테스트가 더 이상 이미지를 생성하지 않는다.** 모델 목록 조회로 확인하므로 크레딧이 차감되지 않는다.
- 정사각형 크기 통일은 **적용하지 않았다.** 장 단위 과금이면 절약 효과 없이 화질만 떨어진다.

## 4. 이미지 호출 기록

- 실패를 포함한 모든 이미지 요청을 `config/image_calls.jsonl`에 기록한다 (시각, 종류, 모델, 상태 코드).
- `config/usage.json`에 `image_requests`, `image_failed_requests`를 추가했다.
- 화면 상단 사용량에 실패 요청 수를 표시한다.

## 5. 인터넷 배포 준비 (Render)

- 저장소: https://github.com/hakzu-lgtm/poly-toon (공개)
- `Dockerfile`: python 3.12-slim에 한글 폰트 `fonts-nanum`을 설치한다. 포트는 `$PORT`를 쓴다.
- `render.yaml`: Render 무료 웹 서비스 설정. 헬스 체크는 `/health`다.
- **환경변수** (Render 화면에서 입력하며 git에는 올리지 않는다):
  - `FACTCHAT_API_KEY`: `config/config.json`이 없을 때 이 키를 사용한다 (`config_store.load`).
  - `APP_PASSWORD`: 값이 있으면 모든 요청에 HTTP 기본 인증을 요구한다. `/health`는 제외된다. 사용자 이름은 아무거나 입력해도 된다.
- 한글 폰트 후보에 리눅스 나눔고딕 경로를 추가했다 (`bubbles.py`, `cover.py`, `layout.py`).
- `outputs/style_previews/`(그림체 미리보기 12장)를 git에 포함했다. 서버에 없으면 12장 × 15 = 180크레딧을 들여 다시 생성하기 때문이다.
- 주의: Render 무료 플랜은 15분 동안 접속이 없으면 잠들고, 재시작하면 `outputs/`와 `config/`가 초기화된다.
  생성한 웹툰은 반드시 내보내기로 내려받아 둘 것.

## 예상 효과 (12패널 스토리 기준)

- 이전: 이미지 약 27장 × 46 = 약 1,240크레딧 (실패 재시도 제외)
- 이후: 이미지 24장 × 15 = 약 360크레딧 (패널당 1칸이면 약 180)

## 다음 작업 (TODO)

1. [ ] 10/1 크레딧 충전 후 `gpt-image-2.5-sunburst`로 한 장 생성해 결과와 **차감량(15)** 확인하기
2. [ ] `quality` low와 medium의 차감량이 같은지 비교하기. 같으면 medium 이상을 사용한다.
3. [ ] 컷 6~12 다시 생성하기 (현재 회색 빈 이미지)
4. [ ] FactChat 대시보드에서 9/30 요청별 차감 내역을 확인해 실패한 `images/edit` 요청이 과금됐는지 확인하기
5. [ ] 편집 요청(`/images/edit`)이 `500`을 내는 원인 조사하기. 새 모델에서는 되는지 1회 테스트한다.
   복구되면 설정에서 "캐릭터 시트 참조"를 켜서 캐릭터 일관성을 확보한다.
6. [ ] `gpt-image-2.5-flare`와 sunburst의 품질 비교하기 (선택)

## 변경 파일 목록

- `backend/factchat_client.py`: quality, 참조 축소, `_post_image` 재시도 규칙, `CreditExhaustedError`, `list_models`, 연결 테스트
- `backend/usage_tracker.py`: `log_image_call`, 실패 요청 카운터
- `backend/config_store.py`: 기본 모델, `image_quality`, `max_frames_per_panel`, `use_reference_images`
- `backend/main.py`: 설정 API 항목 추가, 크레딧 부족 시 스트림 중단, 연결 테스트 모델 전달
- `backend/pipeline/panels.py`: `_fit_layout`, `1-full`/`2-col` 레이아웃, 회색 대체 이미지 제거
- `backend/pipeline/cover.py`: 중복 재시도 제거, 참조 설정 반영
- `backend/pipeline/story.py`: 칸 수 제한 프롬프트, 모델 기본값
- `frontend/index.html`: 이미지 품질, 최대 칸 수, 캐릭터 시트 참조 설정, `app.js?v=9`
- `frontend/app.js`: 위 설정의 저장·불러오기, 실패 요청 표시
- `config/config.json`: git 제외 대상이라 로컬에만 반영됨
