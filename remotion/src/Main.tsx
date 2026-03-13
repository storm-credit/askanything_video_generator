import { AbsoluteFill, Sequence, Video, Audio, Img, staticFile, useCurrentFrame, interpolate } from 'remotion';
import React, { useMemo } from 'react';
import { Captions } from './Captions';

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

export const Main: React.FC<{ cuts: CutProps[] }> = ({ cuts }) => {

  // Precompute start frames to avoid side-effects during render
  const startFrames = useMemo(() => {
    const frames: number[] = [];
    let acc = 0;
    for (const cut of cuts) {
      frames.push(acc);
      acc += cut.duration_in_frames;
    }
    return frames;
  }, [cuts]);

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
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
    </AbsoluteFill>
  );
};
