import { AbsoluteFill, Sequence, Video, Audio, Img, staticFile, useCurrentFrame, interpolate, useVideoConfig } from 'remotion';
import React, { useMemo } from 'react';
import { Captions } from './Captions';

const INTRO_DURATION_FRAMES = 24;  // 1초 @ 24fps
const TITLE_OVERLAY_FRAMES = 60;  // 2.5초 @ 24fps (첫 컷 위 오버레이)
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

// 제목 오버레이 (첫 번째 컷 위에 표시 — 투명 배경)
const TitleOverlay: React.FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 0→0.3초: 페이드인, 마지막 0.4초: 페이드아웃
  const fadeIn = interpolate(frame, [0, fps * 0.3], [0, 1], { extrapolateRight: 'clamp' });
  const fadeOut = interpolate(
    frame,
    [TITLE_OVERLAY_FRAMES - fps * 0.4, TITLE_OVERLAY_FRAMES],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
  const opacity = fadeIn * fadeOut;

  // 살짝 위로 올라오는 애니메이션
  const translateY = interpolate(frame, [0, fps * 0.5], [20, 0], { extrapolateRight: 'clamp' });

  // 밑줄 확장 애니메이션 (0.2→0.8초)
  const lineWidth = interpolate(frame, [fps * 0.2, fps * 0.8], [0, 100], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        opacity,
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          transform: `translateY(${translateY}px)`,
        }}
      >
        {/* 반투명 배경 박스 */}
        <div
          style={{
            backgroundColor: 'rgba(0, 0, 0, 0.55)',
            borderRadius: 16,
            padding: '24px 48px 20px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              color: 'white',
              fontSize: title.length > 10 ? 64 : 80,
              fontWeight: 900,
              fontFamily: 'sans-serif',
              textAlign: 'center',
              lineHeight: 1.3,
              textShadow: '0 0 30px rgba(99, 102, 241, 0.7), 0 2px 8px rgba(0,0,0,0.8)',
            }}
          >
            {title}
          </div>
          {/* 하단 장식 라인 */}
          <div
            style={{
              marginTop: 20,
              height: 3,
              width: `${lineWidth}%`,
              maxWidth: 360,
              background: 'linear-gradient(90deg, transparent, #818cf8, #6366f1, #818cf8, transparent)',
              borderRadius: 2,
            }}
          />
        </div>
      </div>
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

const BGM_VOLUME = 0.15;  // TTS 대비 15% 볼륨

export const Main: React.FC<{
  cuts: CutProps[];
  introImagePath?: string;
  outroImagePath?: string;
  bgmPath?: string;
  title?: string;
}> = ({ cuts, introImagePath, outroImagePath, bgmPath, title }) => {

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

      {/* 제목 오버레이 — 첫 번째 컷 위에 표시 (컷 길이 초과 방지) */}
      {title && cuts.length > 0 && (
        <Sequence from={introFrames} durationInFrames={Math.min(TITLE_OVERLAY_FRAMES, cuts[0].duration_in_frames)}>
          <TitleOverlay title={title} />
        </Sequence>
      )}

      {/* BGM 배경음악 — 전체 영상에 낮은 볼륨으로 루프 */}
      {bgmPath && (
        <Sequence from={0} durationInFrames={totalFrames}>
          <Audio src={staticFile(bgmPath)} volume={BGM_VOLUME} loop />
        </Sequence>
      )}
    </AbsoluteFill>
  );
};
