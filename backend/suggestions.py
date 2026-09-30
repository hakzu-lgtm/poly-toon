"""매 단계 완료 후 "추가하면 좋을 3가지" 생성 (LLM)"""

import json
from backend import factchat_client, config_store

SYSTEM_PROMPT = """\
당신은 웹툰 제작 어시스턴트입니다.
현재 단계와 지금까지의 작업 결과를 보고, 다음에 추가하면 좋을 제안 3가지를 JSON 배열로 반환합니다.

규칙:
- 반드시 정확히 3개의 제안을 반환.
- 각 제안은 현재 단계의 맥락에 맞아야 함.
- 실행 가능하고 구체적인 제안.
- JSON만 출력, 다른 텍스트 없이:

[
  {"title": "제안 제목 (10자 이내)", "desc": "구체적 설명 (30자 이내)", "action": "snake_case_action_id"},
  {"title": "...", "desc": "...", "action": "..."},
  {"title": "...", "desc": "...", "action": "..."}
]

action 값은 프로그램이 식별할 수 있는 영문 스네이크케이스여야 합니다.
"""

STAGE_CONTEXT = {
    0: "설정/API 연결 단계를 완료했습니다. API 키를 입력하고 연결 테스트를 마쳤습니다.",
    1: "웹툰 설정 단계를 완료했습니다. 키워드, 장르, 분위기, 그림체, 컷 수, 등장인물 수 등을 설정했습니다.",
    2: "스토리 생성 단계를 완료했습니다. AI가 시놉시스, 등장인물, 컷별 장면/대사를 생성했습니다.",
    3: "캐릭터 시트 단계를 완료했습니다. 등장인물별 레퍼런스 이미지를 생성했습니다.",
    4: "컷 이미지 생성 단계를 완료했습니다. 각 컷의 장면 이미지를 생성하고 선택했습니다.",
    5: "페이지 배치 단계를 완료했습니다. 컷들을 세로 스크롤 레이아웃으로 배치했습니다.",
    6: "말풍선/대사 합성 단계를 완료했습니다. 한글 대사를 말풍선으로 이미지에 합성했습니다.",
    7: "내보내기 단계를 완료했습니다. PNG/PDF/ZIP으로 결과물을 내보냈습니다.",
}


def generate_suggestions(stage: int, context_summary: str = "") -> list[dict]:
    cfg = config_store.load()

    stage_desc = STAGE_CONTEXT.get(stage, f"Stage {stage}를 완료했습니다.")

    user_msg = f"현재 완료된 단계: Stage {stage}\n{stage_desc}"
    if context_summary:
        user_msg += f"\n\n현재까지의 작업 요약:\n{context_summary}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    raw = factchat_client.chat(
        messages,
        model=cfg["models"].get("suggestions", "gemini-3.5-flash-lite"),
        host=cfg["host"],
        api_key=cfg["api_key"],
        response_json=True,
        max_tokens=1024,
    )

    try:
        result = factchat_client.parse_json_response(raw)
        if isinstance(result, list) and len(result) >= 3:
            return result[:3]
    except (json.JSONDecodeError, KeyError):
        pass

    return [
        {"title": "다음 단계 진행", "desc": "다음 단계로 넘어갑니다.", "action": "next_stage"},
        {"title": "현재 결과 검토", "desc": "생성된 결과를 다시 확인합니다.", "action": "review_current"},
        {"title": "설정 수정", "desc": "이전 단계의 설정을 조정합니다.", "action": "edit_settings"},
    ]
