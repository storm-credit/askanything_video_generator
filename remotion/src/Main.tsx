import { AbsoluteFill, Sequence, Video, Audio, Img, staticFile, useCurrentFrame, interpolate, useVideoConfig } from 'remotion';
import React, { useCallback, useMemo } from 'react';
import { Captions } from './Captions';

const INTRO_DURATION_FRAMES = 24;  // 1초 @ 24fps
const OUTRO_DURATION_FRAMES = 24;  // 1초 @ 24fps

type WordProps = {
  word: string;
  start: number;
  end: number;
};

type CutProps = {
  visual_path: string;
  audio_path: string;
  word_timestamps: WordProps[];
  duration_in_frames: number;
  description?: string;
  emotion?: 'SHOCK' | 'WONDER' | 'TENSION' | 'REVEAL' | 'CALM';
};

// Extract [EMOTION] tag from cut description field
const EMOTION_TAGS = new Set(['SHOCK', 'WONDER', 'TENSION', 'REVEAL', 'CALM']);
const extractEmotion = (cut: CutProps): EmotionTag | undefined => {
  if (cut.emotion && EMOTION_TAGS.has(cut.emotion)) return cut.emotion as EmotionTag;
  if (!cut.description) return undefined;
  const match = cut.description.match(/\[(\w+)\]/);
  if (match && EMOTION_TAGS.has(match[1])) return match[1] as EmotionTag;
  return undefined;
};

const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov'];

// URL에서 쿼리 파라미터/프래그먼트 제거 후 확장자 검사
function isVideoPath(path: string): boolean {
  try {
    const pathname = new URL(path, 'http://dummy').pathname;
    return VIDEO_EXTENSIONS.some(ext => pathname.toLowerCase().endsWith(ext));
  } catch {
    return VIDEO_EXTENSIONS.some(ext => path.toLowerCase().endsWith(ext));
  }
}

// Ken Burns 효과 프리셋: 스타일별 그룹
type KenBurnsPreset = { startScale: number; endScale: number; startX: number; endX: number; startY: number; endY: number };
type CameraStyle = 'auto' | 'dynamic' | 'gentle' | 'static';

const CAMERA_PRESETS: Record<Exclude<CameraStyle, 'auto'>, KenBurnsPreset[]> = {
  dynamic: [
    { startScale: 1.0, endScale: 1.15, startX: 0, endX: -3, startY: 0, endY: -2 },
    { startScale: 1.12, endScale: 1.0, startX: -2, endX: 2, startY: -1, endY: 1 },
    { startScale: 1.0, endScale: 1.1, startX: 2, endX: -2, startY: 0, endY: 0 },
    { startScale: 1.08, endScale: 1.0, startX: 0, endX: 0, startY: 2, endY: -2 },
    { startScale: 1.0, endScale: 1.18, startX: -1, endX: 1, startY: -1, endY: 1 },
    { startScale: 1.15, endScale: 1.02, startX: 3, endX: -1, startY: 0, endY: -1 },
  ],
  gentle: [
    { startScale: 1.0, endScale: 1.05, startX: 0, endX: -1, startY: 0, endY: -0.5 },
    { startScale: 1.04, endScale: 1.0, startX: -0.5, endX: 0.5, startY: 0, endY: 0 },
    { startScale: 1.0, endScale: 1.04, startX: 0.5, endX: -0.5, startY: 0, endY: 0 },
    { startScale: 1.03, endScale: 1.0, startX: 0, endX: 0, startY: 0.5, endY: -0.5 },
  ],
  static: [
    { startScale: 1.0, endScale: 1.0, startX: 0, endX: 0, startY: 0, endY: 0 },
  ],
};

// Emotion → camera preset mapping (overrides round-robin when emotion tag present)
type EmotionTag = 'SHOCK' | 'WONDER' | 'TENSION' | 'REVEAL' | 'CALM';
const EMOTION_CAMERA: Record<EmotionTag, KenBurnsPreset> = {
  SHOCK:   { startScale: 1.0, endScale: 1.2, startX: 0, endX: -4, startY: 0, endY: -3 },
  WONDER:  { startScale: 1.0, endScale: 1.06, startX: -1, endX: 1, startY: 0, endY: -0.5 },
  TENSION: { startScale: 1.08, endScale: 1.12, startX: 0, endX: 0, startY: 1, endY: -1 },
  REVEAL:  { startScale: 1.18, endScale: 1.0, startX: -3, endX: 3, startY: -2, endY: 2 },
  CALM:    { startScale: 1.0, endScale: 1.02, startX: 0, endX: 0, startY: 0, endY: 0 },
};

const KenBurnsImage: React.FC<{ src: string; durationInFrames: number; index: number; cameraStyle?: CameraStyle; emotion?: EmotionTag }> = ({ src, durationInFrames, index, cameraStyle = 'dynamic', emotion }) => {
  const frame = useCurrentFrame();

  // Emotion-based camera takes priority over round-robin
  let preset: KenBurnsPreset;
  // "auto" mode: always use emotion-based camera if available
  const effectiveStyle = cameraStyle === 'auto' ? 'dynamic' : cameraStyle;
  if (emotion && effectiveStyle !== 'static' && EMOTION_CAMERA[emotion]) {
    preset = EMOTION_CAMERA[emotion];
  } else {
    const presets = CAMERA_PRESETS[effectiveStyle] || CAMERA_PRESETS.dynamic;
    preset = presets[index % presets.length];
  }

  const progress = interpolate(frame, [0, durationInFrames], [0, 1], { extrapolateRight: 'clamp' });

  const scale = interpolate(progress, [0, 1], [preset.startScale, preset.endScale]);
  const translateX = interpolate(progress, [0, 1], [preset.startX, preset.endX]);
  const translateY = interpolate(progress, [0, 1], [preset.startY, preset.endY]);

  return (
    <Img
      src={src}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        transform: `scale(${scale}) translate(${translateX}%, ${translateY}%)`,
      }}
    />
  );
};

// 브랜드 인트로 화면 (빠른 페이드인 + 줌 + 페이드아웃)
const BrandIntro: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0→0.2초: 빠른 페이드인
  const opacity = interpolate(frame, [0, fps * 0.2], [0, 1], { extrapolateRight: 'clamp' });
  const scale = interpolate(frame, [0, INTRO_DURATION_FRAMES], [1.0, 1.03], { extrapolateRight: 'clamp' });
  // 마지막 0.2초: 페이드아웃
  const fadeOut = interpolate(
    frame,
    [INTRO_DURATION_FRAMES - fps * 0.2, INTRO_DURATION_FRAMES],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      <Img
        src={src}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity: opacity * fadeOut,
          transform: `scale(${scale})`,
        }}
      />
    </AbsoluteFill>
  );
};

// 브랜드 아웃트로 화면 (빠른 페이드인 + 정지)
const BrandOutro: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, fps * 0.25], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      <Img
        src={src}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          opacity,
        }}
      />
    </AbsoluteFill>
  );
};

const FADE_IN_FRAMES = 6; // 250ms @ 24fps

const FadeIn: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, FADE_IN_FRAMES], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ opacity }}>
      {children}
    </AbsoluteFill>
  );
};

const BGM_VOLUME = 0.25;  // TTS 대비 25% 볼륨 (fallback when no timestamps)
const BGM_VOLUME_SPEECH = 0.15;  // Speech active: duck to 15%
const BGM_VOLUME_SILENCE = 0.35; // No speech: raise to 35%
const BGM_RAMP_FRAMES = 5;       // Smooth transition over 5 frames
const BGM_INTRO_FRAMES = 12;     // 첫 0.5초(12f@24fps) BGM 풀 볼륨 인트로

// Build global word timeline from all cuts with their absolute frame offsets
function buildGlobalWordTimeline(
  cuts: CutProps[],
  startFrames: number[],
  fps: number,
): { startFrame: number; endFrame: number }[] {
  const timeline: { startFrame: number; endFrame: number }[] = [];
  for (let i = 0; i < cuts.length; i++) {
    const cutOffset = startFrames[i];
    for (const w of cuts[i].word_timestamps) {
      timeline.push({
        startFrame: cutOffset + Math.round(w.start * fps),
        endFrame: cutOffset + Math.round(w.end * fps),
      });
    }
  }
  // Sort by startFrame for binary search
  timeline.sort((a, b) => a.startFrame - b.startFrame);
  return timeline;
}

// Type alias for global word timeline segments
type GlobalWordSegment = { startFrame: number; endFrame: number };

// For a given frame, find the nearest speech boundary and compute interpolated BGM volume
// Uses binary search (O(log n)) instead of linear scan
const BGM_FADEOUT_FRAMES = 12;   // 마지막 0.5초(12f@24fps) BGM fade-out → 팝/클릭 방지

function getDynamicBgmVolume(
  frame: number,
  timeline: GlobalWordSegment[],
  totalFrames?: number,
): number {
  if (timeline.length === 0) return BGM_VOLUME;

  // 영상 끝부분 fade-out: 마지막 12프레임에서 볼륨 → 0 (hard cut 방지)
  if (totalFrames && frame >= totalFrames - BGM_FADEOUT_FRAMES) {
    return interpolate(
      frame,
      [totalFrames - BGM_FADEOUT_FRAMES, totalFrames],
      [BGM_VOLUME_SILENCE, 0],
      { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' },
    );
  }

  // 첫 0.5초 인트로: BGM 풀 볼륨으로 시작 → 나레이션 전에 음악 존재감 확보
  if (frame < BGM_INTRO_FRAMES) {
    return BGM_VOLUME_SILENCE;
  }

  // Binary search for speech segment containing frame
  let lo = 0, hi = timeline.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frame < timeline[mid].startFrame) hi = mid - 1;
    else if (frame > timeline[mid].endFrame) lo = mid + 1;
    else return BGM_VOLUME_SPEECH; // inside speech
  }

  // After binary search: hi < lo
  // hi = index of last segment ending before frame (or -1)
  // lo = index of first segment starting after frame (or timeline.length)
  let minDist = Infinity;
  if (hi >= 0) minDist = Math.min(minDist, frame - timeline[hi].endFrame);
  if (lo < timeline.length) minDist = Math.min(minDist, timeline[lo].startFrame - frame);

  // Ramp: smoothly transition from speech volume to silence volume over BGM_RAMP_FRAMES
  if (minDist <= BGM_RAMP_FRAMES) {
    return interpolate(
      minDist,
      [0, BGM_RAMP_FRAMES],
      [BGM_VOLUME_SPEECH, BGM_VOLUME_SILENCE],
      { extrapolateRight: 'clamp' },
    );
  }

  return BGM_VOLUME_SILENCE;
}

// BGM audio with dynamic volume that ducks during speech
const DynamicBgmAudio: React.FC<{
  src: string;
  cuts: CutProps[];
  startFrames: number[];
}> = ({ src, cuts, startFrames }) => {
  const { fps, durationInFrames } = useVideoConfig();

  const globalTimeline = useMemo(
    () => buildGlobalWordTimeline(cuts, startFrames, fps),
    [cuts, startFrames, fps],
  );

  const hasTimestamps = globalTimeline.length > 0;

  const volumeCallback = useCallback(
    (f: number) => getDynamicBgmVolume(f, globalTimeline, durationInFrames),
    [globalTimeline, durationInFrames],
  );

  return (
    <Audio
      src={src}
      volume={hasTimestamps ? volumeCallback : BGM_VOLUME}
      loop
    />
  );
};

export const Main: React.FC<{
  cuts: CutProps[];
  introImagePath?: string;
  outroImagePath?: string;
  bgmPath?: string;
  title?: string;
  cameraStyle?: CameraStyle;
  captionSize?: number;
  captionY?: number;
}> = ({ cuts, introImagePath, outroImagePath, bgmPath, title, cameraStyle = 'dynamic', captionSize = 48, captionY = 28 }) => {

  const introFrames = introImagePath ? INTRO_DURATION_FRAMES : 0;
  const outroFrames = outroImagePath ? OUTRO_DURATION_FRAMES : 0;

  // Precompute start frames (인트로 직후 본편 시작)
  const { startFrames, contentEndFrame, totalFrames } = useMemo(() => {
    const frames: number[] = [];
    let acc = introFrames;
    for (const cut of cuts) {
      frames.push(acc);
      acc += cut.duration_in_frames;
    }
    return { startFrames: frames, contentEndFrame: acc, totalFrames: acc + outroFrames };
  }, [cuts, introFrames, outroFrames]);

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      {/* 브랜드 인트로 (있을 때만) */}
      {introImagePath && (
        <Sequence from={0} durationInFrames={INTRO_DURATION_FRAMES}>
          <BrandIntro src={staticFile(introImagePath)} />
        </Sequence>
      )}

      {/* 본편 컷 시퀀스 */}
      {cuts.map((cut, index) => {
        const startFrame = startFrames[index];

        // staticFile()로 public dir 기준 상대 경로 로드
        const visualSrc = cut.visual_path.startsWith('http') ? cut.visual_path : staticFile(cut.visual_path);
        const audioSrc = cut.audio_path.startsWith('http') ? cut.audio_path : staticFile(cut.audio_path);
        const isVideo = isVideoPath(visualSrc);
        const emotion = extractEmotion(cut);

        return (
          <Sequence key={index} from={startFrame} durationInFrames={cut.duration_in_frames}>
            <FadeIn>
              <AbsoluteFill>
                  {isVideo ? (
                      <Video
                        src={visualSrc}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        loop
                        muted
                      />
                  ) : (
                      <KenBurnsImage src={visualSrc} durationInFrames={cut.duration_in_frames} index={index} cameraStyle={cameraStyle} emotion={emotion} />
                  )}
                  <Audio src={audioSrc} />
                  <Captions wordTimestamps={cut.word_timestamps} captionSize={captionSize} captionY={captionY} emotion={emotion} />
              </AbsoluteFill>
            </FadeIn>
          </Sequence>
        );
      })}

      {/* 브랜드 아웃트로 (있을 때만) */}
      {outroImagePath && (
        <Sequence from={contentEndFrame} durationInFrames={OUTRO_DURATION_FRAMES}>
          <BrandOutro src={staticFile(outroImagePath)} />
        </Sequence>
      )}


      {/* BGM 배경음악 — 전체 영상에 동적 볼륨으로 루프 (speech ducking) */}
      {bgmPath && (
        <Sequence from={0} durationInFrames={totalFrames}>
          <DynamicBgmAudio src={staticFile(bgmPath)} cuts={cuts} startFrames={startFrames} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
