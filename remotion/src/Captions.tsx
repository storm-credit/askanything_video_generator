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

// 감정별 하이라이트 색상
const EMOTION_HIGHLIGHT_COLOR: Record<EmotionTag, string> = {
  SHOCK: '#FF4444',
  WONDER: '#FFB800',
  TENSION: '#FF6600',
  REVEAL: '#00CC66',
  CALM: '#5BB8E8',
};

const getEmotionColor = (emotion?: string): string => {
  if (emotion && emotion in EMOTION_HIGHLIGHT_COLOR) {
    return EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag];
  }
  return '#FFD700'; // default gold
};

const isEmphasisWord = (word: string): boolean => {
  const clean = word.replace(/[.,!?;:'"]/g, '').toLowerCase();
  if (EMPHASIS_PATTERNS.test(clean)) return true;
  if (/^\d/.test(clean)) return true;
  if (clean.length >= 7 && /^[a-z]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  if (clean.length >= 4 && /^[\uAC00-\uD7A3]+$/.test(clean)) return true;
  if (/^[\u30A0-\u30FF]{3,}$/.test(clean)) return true;
  if (clean.length >= 4 && /^[\u4E00-\u9FFF]+$/.test(clean)) return true;
  if (clean.length >= 8 && /^[a-zA-Z\u00C0-\u024F]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  return false;
};

// ── 구간(phrase) 단위로 단어 그룹핑 ──
// Hormozi/MrBeast 스타일: 2-4 단어씩 팝업 → 사라짐 → 다음 구간
// 기준: 시간 갭(0.3s+) 또는 최대 4단어마다 끊기
type Phrase = {
  words: (WordProps & { index: number; emphasis: boolean })[];
  start: number;
  end: number;
};

const buildPhrases = (wordTimestamps: WordProps[]): Phrase[] => {
  const MAX_WORDS_PER_PHRASE = 4;
  const GAP_THRESHOLD = 0.3; // 0.3초 이상 간격이면 구간 분리
  const phrases: Phrase[] = [];
  let current: Phrase['words'] = [];

  for (let i = 0; i < wordTimestamps.length; i++) {
    const w = { ...wordTimestamps[i], index: i, emphasis: isEmphasisWord(wordTimestamps[i].word) };

    if (current.length === 0) {
      current.push(w);
      continue;
    }

    const prevEnd = current[current.length - 1].end;
    const gap = w.start - prevEnd;
    const atMax = current.length >= MAX_WORDS_PER_PHRASE;

    // 구간 끊기: 시간 갭 또는 최대 단어 수 도달
    if (gap >= GAP_THRESHOLD || atMax) {
      phrases.push({
        words: current,
        start: current[0].start,
        end: current[current.length - 1].end,
      });
      current = [w];
    } else {
      current.push(w);
    }
  }

  if (current.length > 0) {
    phrases.push({
      words: current,
      start: current[0].start,
      end: current[current.length - 1].end,
    });
  }

  return phrases;
};

export const Captions: React.FC<{
  wordTimestamps: WordProps[];
  captionSize?: number;
  captionY?: number;
  emotion?: string;
}> = ({ wordTimestamps, captionSize = 48, captionY = 28, emotion }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // 구간 빌드 (메모이제이션)
  const phrases = useMemo(() => buildPhrases(wordTimestamps), [wordTimestamps]);

  // 현재 시간에 해당하는 구간 찾기 (매 프레임 변경되므로 memo 불필요)
  const activePhrase = phrases.find((p) => currentTime >= p.start - 0.1 && currentTime <= p.end + 0.15) || null;

  if (!activePhrase) return null;

  const highlightColor = getEmotionColor(emotion);
  const emphasisColor = emotion && EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag]
    ? EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag]
    : '#FF4444';
  const emphasisR = parseInt(emphasisColor.slice(1, 3), 16);
  const emphasisG = parseInt(emphasisColor.slice(3, 5), 16);
  const emphasisB = parseInt(emphasisColor.slice(5, 7), 16);

  // 구간 등장 진행도 (0~1): 팝업 애니메이션용
  const phraseAge = currentTime - activePhrase.start;
  const popScale = phraseAge < 0.08 ? 0.85 + (phraseAge / 0.08) * 0.15 : 1; // 0.08초 팝업
  const popOpacity = phraseAge < 0.06 ? phraseAge / 0.06 : 1;

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: `${captionY}%` }}>
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        width: '88%',
        gap: '10px',
        textAlign: 'center',
        transform: `scale(${popScale})`,
        opacity: popOpacity,
      }}>
        {activePhrase.words.map((w) => {
          const isActive = currentTime >= w.start && currentTime <= w.end;
          const hasPassed = currentTime > w.end;
          const isEmphasized = isActive && w.emphasis;

          const color = isEmphasized
            ? emphasisColor
            : isActive
              ? highlightColor
              : hasPassed
                ? 'rgba(255, 255, 255, 0.85)'
                : 'rgba(255, 255, 255, 0.5)';

          const textShadow = isEmphasized
            ? `0px 2px 16px rgba(${emphasisR}, ${emphasisG}, ${emphasisB}, 0.6), 0px 0px 8px rgba(${emphasisR}, ${emphasisG}, ${emphasisB}, 0.4), 0px 2px 12px rgba(0, 0, 0, 0.9)`
            : isActive
              ? `0px 2px 12px rgba(0, 0, 0, 0.9), 0px 0px 6px ${highlightColor}4D`
              : '0px 2px 8px rgba(0, 0, 0, 0.8)';

          const scale = isEmphasized ? 1.15 : 1;

          return (
            <span
              key={w.index}
              style={{
                fontFamily: 'Inter, sans-serif',
                fontWeight: isEmphasized ? 900 : 800,
                fontSize: `${captionSize}px`,
                color,
                textShadow,
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
