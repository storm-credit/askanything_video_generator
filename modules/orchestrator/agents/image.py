"""ImageAgent — 병렬 이미지 생성 + 폴백 체인.

api_server.py의 process_cut() 이미지 로직을 래핑.
LLM 호출 없음 — Imagen/Nano Banana/DALL-E 좌표만.
"""

from __future__ import annotations

import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class ImageAgent(BaseAgent):
    name = "ImageAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.image.imagen import generate_image_imagen, generate_image_nano_banana
        from modules.image.dalle import generate_image as generate_image_dalle
        from modules.utils.keys import get_google_key

        if not ctx.cuts:
            yield "WARN|[ImageAgent] 컷이 없습니다.\n"
            return

        ctx.visual_paths = [None] * len(ctx.cuts)
        ctx.cut1_ab_variants = []

        image_label = "Imagen 4" if ctx.image_engine == "imagen" else ("Gemini Nano" if ctx.image_engine == "nano_banana" else "DALL-E")
        yield f"[ImageAgent] {len(ctx.cuts)}컷 이미지 생성 시작 ({image_label})...\n"

        image_semaphore = threading.Semaphore(3)

        def _get_image_key():
            if ctx.image_engine in ("imagen", "nano_banana"):
                return get_google_key(ctx.llm_key, service="imagen",
                                      extra_keys=ctx.gemini_keys_override)
            return ctx.api_key_override

        def _generate_one(i: int, cut: dict) -> tuple[int, str | None, list[str]]:
            if ctx.is_cancelled():
                return i, None, []

            img_path = None
            ab_variants: list[str] = []

            with image_semaphore:
                try:
                    key = _get_image_key()
                    if ctx.image_engine == "imagen":
                        img_path = generate_image_imagen(
                            cut["prompt"], i, ctx.topic_folder, key,
                            model_override=ctx.image_model,
                            gemini_api_keys=ctx.gemini_keys_override,
                            topic=ctx.topic)
                    elif ctx.image_engine == "nano_banana":
                        img_path = generate_image_nano_banana(
                            cut["prompt"], i, ctx.topic_folder, key,
                            gemini_api_keys=ctx.gemini_keys_override,
                            topic=ctx.topic)
                    else:
                        img_path = generate_image_dalle(
                            cut["prompt"], i, ctx.topic_folder, key,
                            topic=ctx.topic)

                    # 컷1은 아래 A/B scoring에서 Vision을 한 번 더 쓰므로 중복 검수를 피한다.
                    if img_path and i != 0:
                        from modules.orchestrator.agents.image_validator import validate_and_retry
                        img_path = validate_and_retry(
                            img_path, cut["prompt"], i, ctx.topic_folder,
                            api_key=key,
                            image_engine=ctx.image_engine,
                            image_model=ctx.image_model,
                            gemini_keys=ctx.gemini_keys_override,
                            topic=ctx.topic,
                        )
                except Exception as exc:
                    # 폴백 체인: Imagen → Nano Banana
                    if ctx.image_engine == "imagen":
                        print(f"[ImageAgent] 컷 {i+1} Imagen 실패 → Nano Banana 폴백: {exc}")
                        try:
                            nb_key = get_google_key(ctx.llm_key, service="nano_banana",
                                                    extra_keys=ctx.gemini_keys_override)
                            img_path = generate_image_nano_banana(
                                cut["prompt"], i, ctx.topic_folder, nb_key,
                                gemini_api_keys=ctx.gemini_keys_override,
                                topic=ctx.topic)
                            if img_path:
                                print(f"[ImageAgent] 컷 {i+1} Nano Banana 폴백 성공")
                        except Exception as nb_exc:
                            print(f"[ImageAgent] 컷 {i+1} Nano Banana도 실패: {nb_exc}")
                    else:
                        print(f"[ImageAgent] 컷 {i+1} 이미지 생성 실패: {exc}")

            # 컷1 A/B 테스트 변형 — 포맷별 최적 구도
            if i == 0 and img_path:
                _format_variants = {
                    "WHO_WINS": [
                        ", dramatic split-frame composition, left vs right, extreme color contrast cool vs warm, both subjects frame-filling",
                        ", bird's eye view of two opposing forces, symmetrical tension, cinematic wide angle",
                    ],
                    "IF": [
                        ", before-after catastrophic transformation, extreme scale shift, saturated apocalyptic colors",
                        ", extreme close-up of the moment of change, shallow depth of field, dramatic lighting shift",
                    ],
                    "EMOTIONAL_SCI": [
                        ", warm golden macro shot, soft ethereal glow, intimate human scale, shallow depth of field",
                        ", overhead perspective with warm amber lighting, gentle soft focus, poetic atmosphere",
                    ],
                    "FACT": [
                        ", extreme close-up shot, macro perspective, filling the entire frame, shallow depth of field",
                        ", ultra wide establishing shot, tiny human silhouette for scale comparison, dramatic deep perspective",
                    ],
                    "COUNTDOWN": [
                        ", dramatic top-down ranking podium, metallic gold trophy glow, spotlights converging on center",
                        ", extreme wide angle panoramic overview, all contenders visible, progressive scale hierarchy",
                    ],
                    "SCALE": [
                        ", extreme size contrast wide angle, miniature vs giant side by side, forced perspective",
                        ", aerial overview with tiny human silhouette against massive backdrop, awe-inspiring scale",
                    ],
                    "PARADOX": [
                        ", bright pastel reassuring scene with subtle dark undertone, hidden duality composition",
                        ", split light-dark frame, half warm sunlight half cold shadow, dramatic contrast",
                    ],
                    "MYSTERY": [
                        ", silhouette in atmospheric fog, single beam of light, noir-style dramatic shadows",
                        ", extreme close-up of mysterious artifact or clue, dark background, spotlight isolation",
                    ],
                }
                fmt = (ctx.format_type or cut.get("format_type") or "FACT").upper()
                variant_suffixes = _format_variants.get(fmt, _format_variants["FACT"])
                for vi, suffix in enumerate(variant_suffixes):
                    try:
                        vkey = _get_image_key()
                        vprompt = cut["prompt"].rstrip(". ,") + suffix
                        vidx = 100 + vi
                        if ctx.image_engine == "imagen":
                            vp = generate_image_imagen(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                model_override=ctx.image_model,
                                gemini_api_keys=ctx.gemini_keys_override,
                                topic=ctx.topic)
                        elif ctx.image_engine == "nano_banana":
                            vp = generate_image_nano_banana(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                gemini_api_keys=ctx.gemini_keys_override,
                                topic=ctx.topic)
                        else:
                            vp = generate_image_dalle(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                topic=ctx.topic)
                        if vp:
                            ab_variants.append(vp)
                    except Exception:
                        pass

            return i, img_path, ab_variants

        executor = ThreadPoolExecutor(max_workers=4)
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(executor, _generate_one, i, cut)
                 for i, cut in enumerate(ctx.cuts)]

        for coro in asyncio.as_completed(tasks):
            i, path, ab_vars = await coro
            ctx.visual_paths[i] = path
            if path:
                ctx.image_count += 1
            if i == 0 and ab_vars:
                ctx.image_count += len(ab_vars)
                ctx.cut1_ab_variants = ab_vars
                # Vision API로 스크롤멈추기 점수 측정 → 최선 선택
                best = _pick_best_cut1(path, ab_vars, ctx.cuts[0].get("script", ""),
                                       ctx.gemini_keys_override or ctx.llm_key)
                if best and best != path:
                    ctx.visual_paths[0] = best
                    yield f"  -> 컷1 A/B 최선 선택 완료 (원본 교체)\n"
                else:
                    yield f"  -> 컷1 A/B 점수 측정 완료 (원본 유지)\n"
                try:
                    from modules.orchestrator.agents.image_validator import validate_and_retry
                    validated = validate_and_retry(
                        ctx.visual_paths[0], ctx.cuts[0].get("prompt", ""), 0, ctx.topic_folder,
                        api_key=ctx.gemini_keys_override or ctx.llm_key,
                        image_engine=ctx.image_engine,
                        image_model=ctx.image_model,
                        gemini_keys=ctx.gemini_keys_override,
                        topic=ctx.topic,
                    )
                    if validated and validated != ctx.visual_paths[0]:
                        ctx.visual_paths[0] = validated
                        yield f"  -> 컷1 최종 이미지 검수 후 교체\n"
                except Exception as exc:
                    yield f"WARN|  -> 컷1 최종 이미지 검수 실패(유지): {exc}\n"
            status = "OK" if ctx.visual_paths[i] else "FAILED"
            yield f"  -> 컷 {i+1} 이미지 {status}\n"

        executor.shutdown(wait=False)

        failed = [i+1 for i, p in enumerate(ctx.visual_paths) if p is None]
        if failed:
            yield f"WARN|[ImageAgent] 이미지 실패: 컷 {failed}\n"
        else:
            yield f"[ImageAgent] 전체 {len(ctx.cuts)}컷 이미지 생성 완료\n"


def _score_scroll_stop(image_path: str, script: str, api_key: str) -> float:
    """Gemini Vision으로 스크롤멈추기 점수 측정 (0.0~1.0).

    채점 기준:
      +0.30  극단적 색상 대비 (찬색↔난색, 밝음↔어둠)
      +0.25  시선 고정 구도 (3분할, 중심 충돌, 드라마틱)
      +0.20  스케일 대비 (극소↔극대, 클로즈업↔와이드)
      +0.20  주제 명확성 + 즉각적 임팩트
      +0.05  텍스트 없음
    """
    try:
        import base64
        from modules.utils.gemini_client import create_gemini_client
        try:
            from google.genai import types as _gtypes
        except ImportError:
            return 0.5

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # API 키 파싱 (쉼표 구분 다중 키 지원)
        _key = api_key.split(",")[0].strip() if api_key and "," in api_key else (api_key or "")
        if not _key:
            return 0.5

        client = create_gemini_client(api_key=_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                _gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                f"""Rate this YouTube Shorts thumbnail's scroll-stop power on 0.0-1.0.

Scoring:
+0.30 if extreme color contrast (cool vs warm, bright vs dark)
+0.25 if eye-locking composition (rule of thirds, central conflict, dramatic angle)
+0.20 if scale contrast (tiny vs huge, extreme close-up vs wide)
+0.20 if subject is instantly clear AND visually shocking/beautiful
+0.05 if no text visible

Script context: "{script[:80]}"

Reply ONLY with a single decimal number like 0.75. Nothing else.""",
            ],
        )
        score = float(response.text.strip().split()[0])
        return max(0.0, min(1.0, score))
    except Exception as e:
        print(f"  [Vision 점수] 에러 (0.5 반환): {e}")
        return 0.5


def _pick_best_cut1(original: str | None, variants: list[str], script: str,
                    api_key: str) -> str | None:
    """원본 + A/B 변형 중 스크롤멈추기 점수 최고 이미지 반환."""
    if not original:
        return None

    candidates = [original] + (variants or [])
    if len(candidates) == 1:
        return original

    try:
        # 병렬 채점 — 순차 대비 ~3x 속도 향상
        valid = [(i, p) for i, p in enumerate(candidates) if p and os.path.exists(p)]
        if not valid:
            return original

        from concurrent.futures import ThreadPoolExecutor, as_completed
        scores: list[tuple[float, str, str]] = []

        with ThreadPoolExecutor(max_workers=len(valid)) as pool:
            futures = {
                pool.submit(_score_scroll_stop, path, script, api_key): (idx, path)
                for idx, path in valid
            }
            for fut in as_completed(futures):
                idx, path = futures[fut]
                try:
                    s = fut.result()
                except Exception:
                    s = 0.5
                label = "원본" if path == original else f"변형{idx}"
                scores.append((s, path, label))
                print(f"  [컷1 Vision] {label}: {s:.2f}")

        if not scores:
            return original

        best_score, best_path, best_label = max(scores, key=lambda x: x[0])
        print(f"  [컷1 A/B] 최선: {best_score:.2f} ({best_label})")
        return best_path
    except Exception as e:
        print(f"  [컷1 A/B] 점수 선택 실패 (원본 유지): {e}")
        return original
