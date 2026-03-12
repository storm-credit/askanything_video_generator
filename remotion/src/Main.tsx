import { AbsoluteFill, Sequence, Video, Audio, Img, useVideoConfig } from 'remotion';
import React from 'react';
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

export const Main: React.FC<{ cuts: CutProps[] }> = ({ cuts }) => {
  const { fps } = useVideoConfig();
  
  let currentStartFrame = 0;

  return (
    <AbsoluteFill style={{ backgroundColor: 'black' }}>
      {cuts.map((cut, index) => {
        const startFrame = currentStartFrame;
        currentStartFrame += cut.duration_in_frames;
        
        // file:/// URI 처리 (Windows 절대 경로 지원)
        const visualSrc = cut.visual_path.startsWith('http') ? cut.visual_path : `file://${cut.visual_path}`;
        const audioSrc = cut.audio_path.startsWith('http') ? cut.audio_path : `file://${cut.audio_path}`;
        const isVideo = visualSrc.toLowerCase().endsWith('.mp4');

        return (
          <Sequence key={index} from={startFrame} durationInFrames={cut.duration_in_frames}>
            <AbsoluteFill>
                {isVideo ? (
                    <Video 
                      src={visualSrc} 
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                      loop 
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
