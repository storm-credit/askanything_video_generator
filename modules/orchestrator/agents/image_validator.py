"""ImageValidator — Gemini Flash Vision으로 이미지 품질 검수.

이미지 생성 후 자동 검수:
1. 프롬프트와 실제 이미지 일치 여부
2. 이미지 품질 (흐릿함, 깨짐, 텍스트 포함)
3. 9:16 세로 구도 적합성

실패 시 1회 재생성.
"""

from __future__ import annotations

import os
import base64


def validate_image(image_path: str, prompt: str, api_key: str = None) -> dict:
    """Gemini Flash Vision으로 이미지 검수.

    Returns:
        {"pass": bool, "reason": str, "score": int (1-10)}
    """
    if not os.path.exists(image_path):
        return {"pass": False, "reason": "파일 없음", "score": 0}

    # 이미지 base64 인코딩
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()

    file_size = os.path.getsize(image_path)
    if file_size < 5000:  # 5KB 미만은 실패
        return {"pass": False, "reason": "파일 크기 너무 작음", "score": 0}

    try:
        from modules.utils.gemini_client import create_gemini_client
        from google.genai import types
    except ImportError as ie:
        print(f"[ImageValidator] import 실패 (통과 처리): {ie}")
        return {"pass": True, "reason": f"import 에러: {str(ie)[:50]}", "score": -1}

    validation_prompt = f"""You are an image quality checker for YouTube Shorts.

Check this image against the prompt and rate it.

PROMPT: {prompt[:200]}

Check these criteria:
1. MATCH: Does the image match the prompt's main subject? (most important)
2. QUALITY: Is the image sharp, clear, not blurry?
3. COMPOSITION: Is it suitable for 9:16 vertical video?
4. TEXT: Does the image contain any text/letters/numbers overlaid? (text = fail)
5. FACE: Does it show a realistic human face close-up? (face = fail)

Respond with ONLY this JSON:
{{"pass": true/false, "score": 1-10, "reason": "brief reason"}}

Rules:
- score 7+ = pass
- score below 7 = fail
- Main subject mismatch = always fail
- Text in image = always fail
- Realistic human face = always fail"""

    try:
        client = create_gemini_client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    parts=[
                        types.Part(text=validation_prompt),
                        types.Part(inline_data=types.Blob(
                            mime_type="image/png",
                            data=base64.b64decode(img_data),
                        )),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                http_options=types.HttpOptions(timeout=30_000),
            ),
        )

        text = (response.text or "").strip()

        # JSON 파싱
        import json, re
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        result = json.loads(text)

        score = result.get("score", 0)
        result["pass"] = score >= 7
        return result

    except Exception as e:
        # 429 에러 시 1회 재시도
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            import time as _time
            _time.sleep(5)
            try:
                from modules.utils.gemini_client import create_gemini_client as _retry_client
                _retry = _retry_client(api_key=api_key)
                _resp = _retry.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=validation_prompt),
                            types.Part(inline_data=types.Blob(mime_type="image/png", data=base64.b64decode(img_data))),
                        ])
                    ],
                    config=types.GenerateContentConfig(temperature=0.1, http_options=types.HttpOptions(timeout=30_000)),
                )
                _text = (_resp.text or "").strip()
                _text = re.sub(r"```json\s*", "", _text)
                _text = re.sub(r"```\s*$", "", _text)
                _result = json.loads(_text)
                _result["pass"] = _result.get("score", 0) >= 7
                return _result
            except Exception:
                pass
        # 최종 실패 시 통과 처리 (검수 때문에 전체가 멈추면 안 됨)
        print(f"[ImageValidator] 검수 실패 (통과 처리): {e}")
        return {"pass": True, "reason": f"검수 에러: {str(e)[:50]}", "score": -1}


def validate_and_retry(image_path: str, prompt: str, cut_index: int,
                       topic_folder: str, api_key: str = None,
                       image_engine: str = "imagen",
                       image_model: str = None,
                       gemini_keys: str = None,
                       topic: str = "") -> str:
    """이미지 검수 + 실패 시 1회 재생성.

    Returns:
        최종 이미지 경로 (원본 또는 재생성된 것)
    """
    # 1차 검수
    result = validate_image(image_path, prompt, api_key)

    if result["pass"]:
        score = result.get("score", "?")
        print(f"  [ImageValidator] 컷 {cut_index+1} 통과 (score={score})")
        return image_path

    print(f"  [ImageValidator] 컷 {cut_index+1} 실패: {result['reason']} (score={result.get('score', 0)})")

    # 재생성 1회
    try:
        from modules.utils.keys import get_google_key

        if image_engine == "imagen":
            from modules.image.imagen import generate_image_imagen
            img_key = get_google_key(None, service="imagen", extra_keys=gemini_keys)
            new_path = generate_image_imagen(
                prompt, cut_index, topic_folder, img_key,
                model_override=image_model,
                gemini_api_keys=gemini_keys,
                topic=topic,
            )
        else:
            from modules.image.dalle import generate_image as generate_image_dalle
            new_path = generate_image_dalle(prompt, cut_index, topic_folder, topic=topic)

        if new_path and os.path.exists(new_path):
            # 2차 검수
            result2 = validate_image(new_path, prompt, api_key)
            if result2["pass"]:
                print(f"  [ImageValidator] 컷 {cut_index+1} 재생성 후 통과 (score={result2.get('score', '?')})")
                return new_path
            else:
                print(f"  [ImageValidator] 컷 {cut_index+1} 재생성도 실패 — 원본 사용")
                return image_path
    except Exception as e:
        print(f"  [ImageValidator] 컷 {cut_index+1} 재생성 실패: {e}")

    return image_path
