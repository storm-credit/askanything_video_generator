"""Day 07 토픽 3,4,5 테스트 배포 — 커스텀 예약 시간."""
import asyncio
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# 테스트 대상 — 오무아무아만 (채널별 언어에 맞는 토픽명)
TASKS = [
    {"topic": "오무아무아정체", "channel": "askanything", "lang": "ko", "hour": 12, "minute": 0},
    {"topic": "Oumuamua unexplained acceleration", "channel": "wonderdrop", "lang": "en", "hour": 12, "minute": 15},
    {"topic": "El objeto interestelar que nadie puede explicar", "channel": "exploratodo", "lang": "es", "hour": 12, "minute": 30},
    {"topic": "El visitante del espacio sin explicación", "channel": "prismtale", "lang": "es", "hour": 12, "minute": 45},
]


async def run_test():
    from modules.gpt.cutter import generate_cuts
    from modules.tts.elevenlabs import generate_tts
    from modules.transcription.whisper import generate_word_timestamps as get_word_timestamps
    from modules.image.imagen import generate_image_imagen
    from modules.video.remotion import create_remotion_video
    from modules.upload.youtube import upload_video as upload_to_youtube
    from modules.utils.keys import get_google_key
    from modules.utils.notify import notify_success, notify_failure
    import os, json

    loop = asyncio.get_running_loop()
    today = datetime.now(KST)

    for task in TASKS:
        topic = task["topic"]
        channel = task["channel"]
        lang = task["lang"]
        publish_time = today.replace(hour=task["hour"], minute=task["minute"], second=0)

        # 예약 시간이 이미 지났으면 내일로
        if publish_time < datetime.now(KST):
            publish_time += timedelta(days=1)

        publish_utc = publish_time.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n{'='*60}")
        print(f"[테스트] {channel} — {topic} (예약: {publish_time.strftime('%m/%d %H:%M KST')})")
        print(f"{'='*60}")

        try:
            # 1. 스크립트
            print(f"  [1/4] 스크립트 생성...")
            result = await loop.run_in_executor(None, lambda: generate_cuts(topic, lang=lang, channel=channel))
            cuts, title, tags, description = result[0], result[2], result[3], result[4] if len(result) > 4 else ""
            topic_folder = result[1] if len(result) > 1 else topic
            print(f"  [1/4] 완료: '{title}' ({len(cuts)}컷)")

            # 2. 이미지
            print(f"  [2/4] 이미지 생성...")
            gemini_keys = os.getenv("GEMINI_API_KEYS", "")
            image_paths = []
            for i, cut in enumerate(cuts):
                try:
                    img_key = get_google_key(None, service="imagen", extra_keys=gemini_keys)
                    img = generate_image_imagen(cut.get("prompt", ""), i, topic_folder, img_key, gemini_api_keys=gemini_keys, topic=topic)
                    image_paths.append(img)
                except Exception as e:
                    print(f"    컷{i+1} 이미지 실패: {e}")
                    image_paths.append(None)
            print(f"  [2/4] 완료: {sum(1 for p in image_paths if p)}장")

            # 3. TTS + 렌더링
            print(f"  [3/4] TTS + 렌더링...")
            audio_paths, word_ts, scripts = [], [], []
            for i, cut in enumerate(cuts):
                script = cut.get("script", "")
                scripts.append(script)
                desc = cut.get("description", cut.get("text", ""))
                emo = None
                for et in ["SHOCK","WONDER","TENSION","REVEAL","URGENCY","DISBELIEF","IDENTITY","CALM"]:
                    if f"[{et}]" in desc:
                        emo = et
                        break
                aud = generate_tts(script, i, topic_folder, language=lang, emotion=emo, channel=channel)
                audio_paths.append(aud)
                if aud:
                    words = get_word_timestamps(aud, language=lang)
                    from modules.transcription.whisper import align_words_with_script
                    words = align_words_with_script(words or [], script)
                    word_ts.append(words)
                else:
                    word_ts.append([])

            valid = [(v,a,s,w) for v,a,s,w in zip(image_paths, audio_paths, scripts, word_ts) if v and a]
            if not valid:
                raise RuntimeError("유효한 컷 없음")

            v_paths, a_paths, s_list, w_list = zip(*valid)
            descs = [cut.get("description", cut.get("text", "")) for cut in cuts[:len(valid)]]

            video_path = create_remotion_video(
                list(v_paths), list(a_paths), list(s_list), list(w_list),
                topic_folder, title=title, channel=channel, descriptions=descs,
            )
            print(f"  [3/4] 완료: {video_path}")

            # 4. YouTube 예약 업로드
            print(f"  [4/4] YouTube 예약 업로드 ({publish_time.strftime('%H:%M KST')})...")
            ch_accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
            ch_id = None
            if os.path.exists(ch_accounts_path):
                with open(ch_accounts_path) as f:
                    accounts = json.load(f)
                ch_id = accounts.get(channel, {}).get("youtube")

            tags_clean = [t for t in tags if t.lower() != "#shorts"]
            full_desc = f"{description}\n\n{' '.join(tags_clean)}".strip()
            video_file = video_path if isinstance(video_path, str) else list(video_path.values())[0]

            yt_result = upload_to_youtube(
                video_path=video_file, title=title, description=full_desc,
                tags=[t.lstrip("#") for t in tags_clean],
                privacy="private", publish_at=publish_utc, channel_id=ch_id,
            )
            print(f"  ✅ 업로드 완료!")
            notify_success(channel, title, video_url=(yt_result or {}).get("url", ""))

        except Exception as e:
            print(f"  ❌ 실패: {e}")
            notify_failure(channel, topic, error=str(e)[:200])
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_test())
