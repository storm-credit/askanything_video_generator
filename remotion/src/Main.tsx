import { AbsoluteFill, Sequence, Video, Audio, Img, staticFile, useCurrentFrame, interpolate, spring, useVideoConfig } from 'remotion';
import React, { useMemo } from 'react';
import { Captions } from './Captions';

const INTRO_DURATION_FRAMES = 48;  // 2초 @ 24fps
const OUTRO_DURATION_FRAMES = 48;  // 2초 @ 24fps

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

// Ken Burns 효과 프리셋: 컷마다 다른 줌/패닝 적용
const KEN_BURNS_PRESETS = [
  { startScale: 1.0, endScale: 1.15, startX: 0, endX: -3, startY: 0, endY: -2 },   // 줌인 + 좌상향
  { startScale: 1.12, endScale: 1.0, startX: -2, endX: 2, startY: -1, endY: 1 },    // 줌아웃 + 우하향
  { startScale: 1.0, endScale: 1.1, startX: 2, endX: -2, startY: 0, endY: 0 },      // 줌인 + 좌패닝
  { startScale: 1.08, endScale: 1.0, startX: 0, endX: 0, startY: 2, endY: -2 },     // 줌아웃 + 상향패닝
  { startScale: 1.0, endScale: 1.18, startX: -1, endX: 1, startY: -1, endY: 1 },    // 대각선 줌인
  { startScale: 1.15, endScale: 1.02, startX: 3, endX: -1, startY: 0, endY: -1 },   // 줌아웃 + 좌패닝
];

const KenBurnsImage: React.FC<{ src: string; durationInFrames: number; index: number }> = ({ src, durationInFrames, index }) => {
  const frame = useCurrentFrame();
  const preset = KEN_BURNS_PRESETS[index % KEN_BURNS_PRESETS.length];

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

// 브랜드 인트로 화면 (페이드인 + 살짝 줌)
const BrandIntro: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0→0.5초: 페이드인, 0→2초: 살짝 줌인
  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], { extrapolateRight: 'clamp' });
  const scale = interpolate(frame, [0, INTRO_DURATION_FRAMES], [1.0, 1.05], { extrapolateRight: 'clamp' });
  // 마지막 0.3초: 페이드아웃
  const fadeOut = interpolate(
    frame,
    [INTRO_DURATION_FRAMES - fps * 0.3, INTRO_DURATION_FRAMES],
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

// 브랜드 아웃트로 화면 (페이드인 + 정지)
const BrandOutro: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0→0.5초: 페이드인
  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], { extrapolateRight: 'clamp' });

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

export const Main: React.FC<{ cuts: CutProps[]; introImagePath?: string; outroImagePath?: string }> = ({ cuts, introImagePath, outroImagePath }) => {

  const introFrames = introImagePath ? INTRO_DURATION_FRAMES : 0;
  const outroFrames = outroImagePath ? OUTRO_DURATION_FRAMES : 0;

  // Precompute start frames (인트로 길이만큼 오프셋)
  const { startFrames, contentEndFrame } = useMemo(() => {
    const frames: number[] = [];
    let acc = introFrames;
    for (const cut of cuts) {
      frames.push(acc);
      acc += cut.duration_in_frames;
    }
    return { startFrames: frames, contentEndFrame: acc };
  }, [cuts, introFrames]);

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

        // staticFile()로 public dir (assets/) 기준 상대 경로 로드
        const visualSrc = cut.visual_path.startsWith('http') ? cut.visual_path : staticFile(cut.visual_path);
        const audioSrc = cut.audio_path.startsWith('http') ? cut.audio_path : staticFile(cut.audio_path);
        const isVideo = isVideoPath(visualSrc);

        return (
          <Sequence key={index} from={startFrame} durationInFrames={cut.duration_in_frames}>
            <AbsoluteFill>
                {isVideo ? (
                    <Video
                      src={visualSrc}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      loop
                      muted
                    />
                ) : (
                    <KenBurnsImage src={visualSrc} durationInFrames={cut.duration_in_frames} index={index} />
                )}
                <Audio src={audioSrc} />
                <Captions wordTimestamps={cut.word_timestamps} />
            </AbsoluteFill>
          </Sequence>
        );
      })}

      {/* 브랜드 아웃트로 (있을 때만) */}
      {outroImagePath && (
        <Sequence from={contentEndFrame} durationInFrames={OUTRO_DURATION_FRAMES}>
          <BrandOutro src={staticFile(outroImagePath)} />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
