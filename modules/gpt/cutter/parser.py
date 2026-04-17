import json
import re
from typing import Any

_YT_CONTENT_SEP = "\n\n[원본 영상 내용]\n"

def _sanitize_llm_input(text: str, max_len: int = 2000) -> str:
    """LLM 프롬프트에 주입되는 외부 텍스트에서 인젝션 패턴을 제거."""
    # 대괄호/중괄호 지시문 패턴 제거
    text = re.sub(r'\[(?:SYSTEM|INST|INSTRUCTION|system|inst)\]', '', text)
    text = re.sub(r'(?i)ignore\s+(all\s+)?previous\s+instructions?', '', text)
    text = re.sub(r'(?i)you\s+are\s+now\s+', '', text)
    return text[:max_len].strip()

def _split_yt_topic(topic: str) -> tuple[str, str]:
    """YouTube 자막이 포함된 topic을 (제목, 자막내용)으로 분리. 자막 없으면 ('', '')."""
    if _YT_CONTENT_SEP in topic:
        title, content = topic.split(_YT_CONTENT_SEP, 1)
        return title.strip(), content.strip()
    # 구분자 없이 [원본 영상 내용]만 있는 경우 (trailing newline 없음)
    marker = "\n\n[원본 영상 내용]"
    if marker in topic:
        title = topic.split(marker, 1)[0].strip()
        return title, ""
    return topic, ""


_VALID_EMOTIONS = {
    "[SHOCK]", "[WONDER]", "[TENSION]", "[REVEAL]", "[URGENCY]", "[DISBELIEF]", "[IDENTITY]", "[CALM]", "[LOOP]",
    "[SETUP]", "[CHAIN_1]", "[CHAIN_2]", "[CHAIN_3]", "[ESCALATE]", "[BUILD]", "[CLIMAX]", "[PIVOT]",
}

def _sanitize_cuts(cuts_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    cuts = []
    for cut in cuts_data:
        prompt = cut.get("image_prompt", "").strip()
        script = cut.get("script", "").strip().strip('"""')
        description = cut.get("description", "").strip()
        if not prompt or not script:
            print(f"  [경고] 빈 컷 제거됨: prompt={bool(prompt)}, script={bool(script)}, desc='{description[:30]}'")
            continue
        # 감정 태그 누락 시 기본값 추가 (Remotion 카메라 프리셋 연동)
        if not any(tag in description for tag in _VALID_EMOTIONS):
            description += " [WONDER]"
        cuts.append({"text": description, "description": description, "prompt": prompt, "script": script})
    return cuts


def _clean_json_string(s: str) -> str:
    """LLM이 반환하는 흔한 JSON 오류를 자동 수정."""
    s = re.sub(r',(\s*[}\]])', r'\1', s)  # trailing comma 제거
    s = s.replace('\n', ' ')  # 줄바꿈 → 공백 (LLM JSON 복구용)
    return s


def _extract_json(text: str) -> dict | list | None:
    """LLM 응답에서 JSON을 추출합니다. 마크다운 코드블록 래핑도 처리. 실패 시 None."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return json.loads(_clean_json_string(text))
        except json.JSONDecodeError:
            return None


def _parse_cuts(content: str) -> tuple[list[dict[str, str]], str, list[str], str]:
    """LLM 응답 텍스트에서 cuts 데이터, 제목, 태그, 설명을 파싱합니다."""
    if not content:
        raise ValueError("LLM 응답 content가 비어 있습니다.")
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ValueError(f"LLM 응답이 올바른 JSON 형식이 아닙니다: {content[:200]}")
    cuts = _sanitize_cuts(data.get("cuts", []))
    if not cuts:
        raise ValueError("LLM 응답에 유효한 cuts가 없습니다.")
    title = data.get("title", "").strip()
    tags = data.get("tags", [])
    description = data.get("description", "").strip()
    return cuts, title, tags, description
