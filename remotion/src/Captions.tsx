import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import React, { useMemo } from 'react';

type WordProps = {
  word: string;
  start: number;
  end: number;
};

// Emphasis detection: numbers, exclamations, long words (high-info density)
// Based on Dual Coding Theory (Paivio 1986) — highlight ≤20% of words for optimal recall
const EMPHASIS_PATTERNS = /^(\d[\d,.]*[%배만억조x]?|미쳤|소름|진짜|ㄹㅇ|대박|역대|최초|insane|crazy|impossible|dead|never|every|all|million|billion|trillion|forever|nothing|destroy|vanish|disappear|survive|freeze|explode)/i;

// English stopwords — common function words that should NOT be emphasized even if long
const EN_STOPWORDS = new Set([
  'because', 'through', 'should', 'before', 'after', 'about', 'between',
  'during', 'without', 'within', 'around', 'already', 'always', 'another',
  'become', 'behind', 'believe', 'beside', 'beyond', 'cannot', 'could',
  'enough', 'itself', 'itself', 'might', 'nothing', 'people', 'really',
  'should', 'something', 'sometimes', 'still', 'their', 'there', 'these',
  'thing', 'think', 'those', 'though', 'under', 'until', 'where', 'which',
  'while', 'would', 'actually', 'however', 'together',
]);

const isEmphasisWord = (word: string): boolean => {
  const clean = word.replace(/[.,!?;:'"]/g, '').toLowerCase();
  if (EMPHASIS_PATTERNS.test(clean)) return true;
  if (/^\d/.test(clean)) return true;
  // English: 6+ chars, not a stopword (content words only)
  if (clean.length >= 6 && /^[a-z]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  // Korean: 4+ chars (Korean words are inherently shorter, most 4+ char words are content-rich)
  if (clean.length >= 4 && /^[\u3131-\uD79D]+$/.test(clean)) return true;
  return false;
};

export const Captions: React.FC<{ wordTimestamps: WordProps[]; captionSize?: number; captionY?: number }> = ({ wordTimestamps, captionSize = 48, captionY = 28 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  const quantizedTime = Math.floor(currentTime * 10) / 10;

  const visibleWords = useMemo(() => {
    const windowStart = quantizedTime - 1;
    const windowEnd = quantizedTime + 1;
    return wordTimestamps
      .map((w, index) => ({ ...w, index, emphasis: isEmphasisWord(w.word) }))
      .filter((w) => w.end >= windowStart && w.start <= windowEnd);
  }, [wordTimestamps, quantizedTime]);

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: `${captionY}%` }}>
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

          const isEmphasized = isActive && w.emphasis;

          const color = isEmphasized
            ? '#FF4444'
            : isActive
              ? '#FFD700'
              : 'rgba(255, 255, 255, 0.6)';

          const textShadow = isEmphasized
            ? '0px 2px 16px rgba(255, 68, 68, 0.6), 0px 0px 8px rgba(255, 68, 68, 0.4), 0px 2px 12px rgba(0, 0, 0, 0.9)'
            : isActive
              ? '0px 2px 12px rgba(0, 0, 0, 0.9), 0px 0px 6px rgba(255, 215, 0, 0.3)'
              : '0px 2px 8px rgba(0, 0, 0, 0.8)';

          const scale = isEmphasized ? 1.15 : 1;

          return (
            <span
              key={w.index}
              style={{
                fontFamily: 'Inter, sans-serif',
                fontWeight: isEmphasized ? 900 : 800,
                fontSize: `${captionSize}px`,
                color: color,
                textShadow: textShadow,
                WebkitTextStroke: '1.5px rgba(0, 0, 0, 0.5)',
                lineHeight: '1.3',
                display: 'inline-block',
                transform: `scale(${scale})`,
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
