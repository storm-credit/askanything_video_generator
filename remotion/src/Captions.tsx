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

  // 성능 최적화: 100ms 단위로 양자화하여 useMemo 재계산 빈도 감소 (24fps → ~2.4 updates/sec)
  const quantizedTime = Math.floor(currentTime * 10) / 10;

  const visibleWords = useMemo(() => {
    const windowStart = quantizedTime - 1;
    const windowEnd = quantizedTime + 1;
    return wordTimestamps
      .map((w, index) => ({ ...w, index }))
      .filter((w) => w.end >= windowStart && w.start <= windowEnd);
  }, [wordTimestamps, quantizedTime]);

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
          const isActive = quantizedTime >= w.start && quantizedTime <= w.end;
          const hasPassed = quantizedTime > w.end;
          const isVisible = quantizedTime >= w.start - 0.5;

          if (!isVisible && !hasPassed && !isActive) return null;

          const wordStartFrame = Math.round(w.start * fps);
          const elapsed = frame - wordStartFrame;
          // spring 최적화: 10프레임 이후 settled → 계산 스킵
          const scale = elapsed > 10 ? 1 : spring({
            fps,
            frame: elapsed,
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
