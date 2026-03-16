import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import React, { useMemo } from 'react';

type WordProps = {
  word: string;
  start: number;
  end: number;
};

// Emphasis detection: numbers, power words, impact vocabulary
// Based on Dual Coding Theory (Paivio 1986) — highlight ≤20% of words for optimal recall
// Strategy: explicit allow-list (EMPHASIS) > explicit deny-list (STOPWORDS) > length heuristic
const EMPHASIS_PATTERNS = /^(\d[\d,.]*[%배만억조x]?|미쳤|미침|소름|진짜|ㄹㅇ|대박|역대|최초|헐|insane|crazy|impossible|dead|never|every|million|billion|trillion|forever|nothing|destroy|vanish|disappear|survive|freeze|explode|entire|massive|infinite|absolute|unbelievable|incredible|shocking|terrifying)$/i;

// Common function words — should NOT be emphasized even if 7+ chars
const EN_STOPWORDS = new Set([
  'because', 'through', 'should', 'before', 'after', 'about', 'between',
  'during', 'without', 'within', 'around', 'already', 'always', 'another',
  'become', 'behind', 'believe', 'beside', 'beyond', 'cannot', 'enough',
  'itself', 'might', 'people', 'really', 'something', 'sometimes', 'still',
  'their', 'there', 'these', 'thing', 'think', 'those', 'though', 'under',
  'until', 'where', 'which', 'while', 'would', 'could', 'actually',
  'however', 'together', 'against', 'minutes', 'seconds', 'degrees',
  'basically', 'literally', 'everything', 'anything', 'someone', 'another',
  'getting', 'looking', 'turning', 'making', 'having', 'being', 'going',
]);

type EmotionTag = 'SHOCK' | 'WONDER' | 'TENSION' | 'REVEAL' | 'CALM';

const EMOTION_HIGHLIGHT_COLOR: Record<EmotionTag, string> = {
  SHOCK: '#FF4444',
  WONDER: '#FFD700',
  TENSION: '#FF8C00',
  REVEAL: '#00FF88',
  CALM: '#87CEEB',
};

const getEmotionColor = (emotion?: string): string => {
  if (emotion && emotion in EMOTION_HIGHLIGHT_COLOR) {
    return EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag];
  }
  return '#FFD700'; // default gold
};

const isEmphasisWord = (word: string): boolean => {
  const clean = word.replace(/[.,!?;:'"]/g, '').toLowerCase();
  // 1) Explicit power words — always emphasize
  if (EMPHASIS_PATTERNS.test(clean)) return true;
  // 2) Numbers — always emphasize (data = impact)
  if (/^\d/.test(clean)) return true;
  // 3) English content words: 7+ chars, not a stopword (stricter threshold)
  if (clean.length >= 7 && /^[a-z]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  // 4) Korean: 4+ Hangul syllables (most 4+ syllable Korean words carry high info density)
  if (clean.length >= 4 && /^[\uAC00-\uD7A3]+$/.test(clean)) return true;
  // 5) Japanese: katakana words (foreign/technical loanwords are attention-grabbing)
  if (/^[\u30A0-\u30FF]{3,}$/.test(clean)) return true;
  // 6) Chinese: 4+ character words (longer compounds carry high info density)
  if (clean.length >= 4 && /^[\u4E00-\u9FFF]+$/.test(clean)) return true;
  // 7) European languages (Spanish, French, German, Portuguese, etc.): 8+ chars
  if (clean.length >= 8 && /^[a-zA-Z\u00C0-\u024F]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  return false;
};

export const Captions: React.FC<{ wordTimestamps: WordProps[]; captionSize?: number; captionY?: number; emotion?: string }> = ({ wordTimestamps, captionSize = 48, captionY = 28, emotion }) => {
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
          const highlightColor = getEmotionColor(emotion);

          const color = isEmphasized
            ? '#FF4444'
            : isActive
              ? highlightColor
              : 'rgba(255, 255, 255, 0.6)';

          const highlightGlow = `0px 2px 12px rgba(0, 0, 0, 0.9), 0px 0px 6px ${highlightColor}4D`;

          const textShadow = isEmphasized
            ? '0px 2px 16px rgba(255, 68, 68, 0.6), 0px 0px 8px rgba(255, 68, 68, 0.4), 0px 2px 12px rgba(0, 0, 0, 0.9)'
            : isActive
              ? highlightGlow
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
