import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring } from 'remotion';
import React, { useMemo } from 'react';

type WordProps = {
  word: string;
  start: number;
  end: number;
};

export const Captions: React.FC<{ wordTimestamps: WordProps[] }> = ({ wordTimestamps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // 성능 최적화: currentTime ± 1초 범위의 단어만 필터링
  const visibleWords = useMemo(() => {
    const windowStart = currentTime - 1;
    const windowEnd = currentTime + 1;
    return wordTimestamps
      .map((w, index) => ({ ...w, index }))
      .filter((w) => w.end >= windowStart && w.start <= windowEnd);
  }, [wordTimestamps, currentTime]);

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', top: '25%' }}>
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        width: '80%',
        gap: '20px',
        textAlign: 'center'
      }}>
        {visibleWords.map((w) => {
          const isActive = currentTime >= w.start && currentTime <= w.end;
          const hasPassed = currentTime > w.end;
          const isVisible = currentTime >= w.start - 0.5;

          if (!isVisible && !hasPassed && !isActive) return null;

          const wordStartFrame = Math.round(w.start * fps);
          const scale = spring({
            fps,
            frame: frame - wordStartFrame,
            config: {
              damping: 12,
              stiffness: 200,
              mass: 0.5,
            },
            durationInFrames: 10,
          });

          const color = isActive ? '#FFD700' : 'white';
          const transformScale = isActive ? 1 + (scale * 0.15) : 1;
          const textShadow = isActive
                ? '0px 0px 20px rgba(255, 215, 0, 0.8), 4px 4px 0px rgba(0,0,0,1)'
                : '4px 4px 0px rgba(0,0,0,1)';

          return (
            <span
              key={w.index}
              style={{
                fontFamily: 'Inter, sans-serif',
                fontWeight: 900,
                fontSize: isActive ? '120px' : '90px',
                color: color,
                textTransform: 'uppercase',
                transform: `scale(${transformScale})`,
                textShadow: textShadow,
                WebkitTextStroke: '3px black',
                lineHeight: '1.2',
                display: 'inline-block'
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
