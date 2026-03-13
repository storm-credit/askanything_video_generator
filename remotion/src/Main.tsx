import { AbsoluteFill, Sequence, Video, Audio, Img, staticFile } from 'remotion';
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
                    // 켄번 (줌인) 효과는 CSS 애니메이션 또는 Remotion의 interpolate로 구현 가능
                    // 단순화를 위해 objectFit: cover 적용
                    <Img 
                      src={visualSrc} 
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                    />
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
