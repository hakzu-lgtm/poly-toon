"""Stage 2: 스토리 생성 — 장(Chapter) 단위 분할 호출"""

from backend import factchat_client, config_store
from backend.pipeline import panels

SYSTEM_PROMPT_OUTLINE = """\
당신은 한국어 웹툰 시나리오 전문 작가입니다.
사용자 설정을 기반으로 웹툰의 전체 구조(제목, 시놉시스, 등장인물, 표지 장면)를 JSON으로 작성합니다.

반드시 아래 JSON 구조만 출력하세요. 설명이나 마크다운 없이 순수 JSON만:

{
  "title": "웹툰 제목",
  "synopsis": "전체 줄거리 요약 (3~5문장, 기승전결)",
  "cover_scene": "표지에 사용할 핵심 장면 묘사 (영어, 이미지 프롬프트용으로 상세하게)",
  "characters": [
    {
      "id": "char_1",
      "name": "캐릭터 이름",
      "role": "주인공/조연/기타",
      "appearance": "외모 상세 묘사 (영어)",
      "outfit": "의상 상세 묘사 (영어)",
      "personality": "성격 묘사 (한국어)"
    }
  ],
  "chapter_summaries": [
    {"chapter_number": 1, "chapter_title": "장 제목", "summary": "이 장의 줄거리 1~2문장"}
  ]
}

- characters의 appearance, outfit, cover_scene은 영어로 작성.
- 등장인물 수와 장 수는 사용자 지정에 맞춤.
"""

SYSTEM_PROMPT_CHAPTER = """\
당신은 한국어 웹툰 시나리오 전문 작가입니다.
주어진 전체 줄거리와 등장인물 정보를 바탕으로, 지정된 장(chapter)의 컷별 시나리오를 JSON으로 작성합니다.

반드시 아래 JSON 구조만 출력하세요:

{
  "chapter_number": 1,
  "chapter_title": "장 제목",
  "panels": [
    {
      "panel_number": 1,
      "layout": "2-row",
      "frames": [
        {"frame": 1, "shot_type": "wide shot", "scene": "프레임 장면 묘사 (영어)"},
        {"frame": 2, "shot_type": "close-up", "scene": "프레임 장면 묘사 (영어)"}
      ],
      "characters_in_scene": ["char_1"],
      "dialogue": [
        {"character": null, "text": "나레이션 (한국어)", "type": "narration"},
        {"character": "char_1", "text": "짧은 대사 (한국어)", "type": "speech", "frame": 1},
        {"character": "char_2", "text": "속마음", "type": "thought", "frame": 2}
      ],
      "mood": "이 컷의 분위기 (영어)"
    }
  ]
}

중요 규칙:
- 각 panel의 frames는 {max_frames}개 이하. frame 하나가 이미지 한 장이므로 꼭 필요할 때만 나눔.
- shot_type 종류: "wide shot", "medium shot", "close-up", "extreme close-up", "over-the-shoulder", "bird's eye", "low angle", "reaction shot"
- layout은 아래 목록에서만 고르고, frames 수가 layout의 칸 수와 정확히 같아야 함:
{layout_guide}

컷 분할 연출 원칙 (실제 웹툰처럼):
- 장면의 역할에 맞는 layout을 고름. 상황 소개는 넓은 한 칸, 대화는 좌우 칸, 사건·충격은 사선 분할,
  연속 동작은 사선으로 쌓은 칸, 물건 나열은 가로 띠 여러 칸, 결심·결론은 크게.
- 같은 layout을 연속으로 쓰지 말고, 1칸 컷과 여러 칸 컷을 섞어 리듬을 만듦.
- 칸이 여러 개면 frame 순서가 읽는 순서(위→아래, 왼쪽→오른쪽)이며, 각 frame의 크기·모양에 맞는 shot_type을 씀
  (좁은 띠 칸은 클로즈업이나 물건, 크고 긴 칸은 전신·주인공).
- 각 frame의 scene은 영어로 (이미지 프롬프트용).
- panel마다 shot_type을 바꿔 시각적 변화를 줌.
- dialogue의 text는 한국어.

대사 규칙 (말풍선이 그림을 가리지 않도록):
- 대사 한 개는 20자 안팎의 짧은 한 마디. 긴 말은 핵심만 남기거나 다음 컷으로 나눔.
- 한 panel의 speech/thought는 2~3개까지. 꼭 필요하지 않으면 1개도 좋음.
- 나레이션(type "narration")은 장면 전환·시간 경과처럼 꼭 필요할 때만, 한 panel에 1개, 30자 이내.
- speech/thought에는 "frame"(그 대사가 나오는 칸 번호, 1부터)을 반드시 적고, 말하는 인물이 그 칸에 등장해야 함.
- type 종류: "speech"(말), "thought"(속마음), "narration"(나레이션).
- panel_number는 지정된 시작 번호부터 연속.
- 컷 수는 사용자가 지정한 수에 정확히 맞춤.
"""


def generate_story(settings: dict) -> dict:
    cfg = config_store.load()

    chapters_config = settings.get("chapters_config", [])
    chapter_count = settings.get("chapter_count", 1)
    if not chapters_config:
        pc = settings.get("panel_count", 6)
        chapters_config = [{"chapter": i + 1, "panel_count": pc} for i in range(chapter_count)]

    # 1단계: 전체 구조 생성
    outline_msg = (
        f"다음 설정으로 웹툰의 전체 구조를 만들어주세요:\n"
        f"- 핵심 키워드: {settings['keywords']}\n"
        f"- 장르: {settings['genre']}\n"
        f"- 분위기: {settings['mood']}\n"
        f"- 그림체: {settings['art_style']}\n"
        f"- 장 수: {chapter_count}장\n"
        f"- 등장인물 수: {settings['character_count']}명\n"
        f"- 대사 톤: {settings['dialogue_tone']}\n"
    )
    if settings.get("extra_notes"):
        outline_msg += f"- 추가 요청: {settings['extra_notes']}\n"

    raw_outline = factchat_client.chat(
        [{"role": "system", "content": SYSTEM_PROMPT_OUTLINE},
         {"role": "user", "content": outline_msg}],
        model=cfg["models"]["story"],
        host=cfg["host"],
        api_key=cfg["api_key"],
        max_tokens=4096,
    )
    outline = factchat_client.parse_json_response(raw_outline)

    # 2단계: 장별 컷 시나리오 생성
    panel_start = 1
    chapters = []

    for ch_cfg in chapters_config:
        ch_num = ch_cfg["chapter"]
        pc = ch_cfg["panel_count"]
        ch_summary = ""
        for cs in outline.get("chapter_summaries", []):
            if cs.get("chapter_number") == ch_num:
                ch_summary = cs.get("summary", "")
                break

        chars_info = "\n".join(
            f"- {c['name']}({c['id']}): {c.get('appearance','')}, {c.get('personality','')}"
            for c in outline.get("characters", [])
        )

        chapter_msg = (
            f"전체 줄거리: {outline.get('synopsis', '')}\n"
            f"등장인물:\n{chars_info}\n\n"
            f"이 장 정보:\n"
            f"- {ch_num}장: {ch_summary}\n"
            f"- 컷 수: {pc}컷\n"
            f"- panel_number 시작: {panel_start}\n"
            f"- 대사 톤: {settings['dialogue_tone']}\n"
        )

        max_frames = cfg.get("max_frames_per_panel", 3)
        raw_chapter = factchat_client.chat(
            [{"role": "system", "content": SYSTEM_PROMPT_CHAPTER
              .replace("{max_frames}", str(max_frames))
              .replace("{layout_guide}", panels.layout_guide(max_frames))},
             {"role": "user", "content": chapter_msg}],
            model=cfg["models"].get("panel_prompt", "claude-sonnet-5-5"),
            host=cfg["host"],
            api_key=cfg["api_key"],
            max_tokens=4096,
        )
        ch_data = factchat_client.parse_json_response(raw_chapter)
        chapters.append(ch_data)
        panel_start += pc

    story = {
        "title": outline.get("title", ""),
        "synopsis": outline.get("synopsis", ""),
        "cover_scene": outline.get("cover_scene", ""),
        "characters": outline.get("characters", []),
        "chapters": chapters,
    }

    return story
