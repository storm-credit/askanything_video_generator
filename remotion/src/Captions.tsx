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

  // 성능 최적화: 100ms 단위로 양자화하여 useMemo 재계산 빈도 감소
  const quantizedTime = Math.floor(currentTime * 10) / 10;

  const visibleWords = useMemo(() => {
    const windowStart = quantizedTime - 1;
    const windowEnd = quantizedTime + 1;
    return wordTimestamps
      .map((w, index) => ({ ...w, index }))
      .filter((w) => w.end >= windowStart && w.start <= windowEnd);
  }, [wordTimestamps, quantizedTime]);

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: '15%' }}>
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        width: '88%',
        gap: '8px',
        textAlign: 'center'
      }}>
        {visibleWords.map((w) => {
          const isActive = quantizedTime >= w.start && quantizedTime <= w.end;
          const hasPassed = quantizedTime > w.end;
          const isVisible = quantizedTime >= w.start - 0.5;

          if (!isVisible && !hasPassed && !isActive) return null;

          const wordStartFrame = Math.round(w.start * fps);
          const elapsed = frame - wordStartFrame;
          const scale = elapsed > 10 ? 1 : spring({
            fps,
            frame: elapsed,
            config: {
              damping: 14,
              stiffness: 180,
              mass: 0.4,
            },
            durationInFrames: 10,
          });

          const color = isActive ? '#FFFFFF' : 'rgba(255, 255, 255, 0.6)';
          const transformScale = isActive ? 1 + (scale * 0.08) : 1;
          const textShadow = isActive
            ? '0px 2px 12px rgba(0, 0, 0, 0.9), 0px 0px 4px rgba(0, 0, 0, 0.7)'
            : '0px 2px 8px rgba(0, 0, 0, 0.8)';

          return (
            <span
              key={w.index}
              style={{
                fontFamily: 'Inter, sans-serif',
                fontWeight: 800,
                fontSize: isActive ? '56px' : '48px',
                color: color,
                transform: `scale(${transformScale})`,
                textShadow: textShadow,
                WebkitTextStroke: '1.5px rgba(0, 0, 0, 0.5)',
                lineHeight: '1.3',
                display: 'inline-block',
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
