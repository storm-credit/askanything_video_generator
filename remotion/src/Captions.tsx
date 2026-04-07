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

type EmotionTag = 'SHOCK' | 'WONDER' | 'TENSION' | 'REVEAL' | 'URGENCY' | 'DISBELIEF' | 'IDENTITY' | 'CALM';

// 자막 색상 — 노랑 통일 (감정별 색 변경은 쇼츠에서 산만함)
const HIGHLIGHT_COLOR = '#FFE600';

const EMOTION_HIGHLIGHT_COLOR: Record<EmotionTag, string> = {
  SHOCK: HIGHLIGHT_COLOR,
  WONDER: HIGHLIGHT_COLOR,
  TENSION: HIGHLIGHT_COLOR,
  REVEAL: HIGHLIGHT_COLOR,
  URGENCY: HIGHLIGHT_COLOR,
  DISBELIEF: HIGHLIGHT_COLOR,
  IDENTITY: HIGHLIGHT_COLOR,
  CALM: HIGHLIGHT_COLOR,
};

const getEmotionColor = (_emotion?: string): string => {
  return HIGHLIGHT_COLOR;
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

export const Captions: React.FC<{ wordTimestamps: WordProps[]; captionSize?: number; captionY?: number; emotion?: string; channel?: string }> = ({ wordTimestamps, captionSize = 48, captionY = 28, emotion, channel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // 구(phrase) 단위 그룹핑: CJK는 3단어, 라틴은 4단어씩 묶어서 고정 표시
  const phrases = useMemo(() => {
    const groups: { words: (WordProps & { index: number; emphasis: boolean })[]; start: number; end: number }[] = [];
    // 한국어/일본어/중국어 단어가 포함되면 3단어로 제한 (줄 넘김 방지)
    const hasCJK = wordTimestamps.some(w => /[\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF]/.test(w.word));
    const MAX_WORDS_PER_PHRASE = hasCJK ? 3 : 4;
    let current: (WordProps & { index: number; emphasis: boolean })[] = [];

    wordTimestamps.forEach((w, index) => {
      const entry = { ...w, index, emphasis: isEmphasisWord(w.word) };
      if (current.length === 0) {
        current.push(entry);
      } else {
        const gap = w.start - current[current.length - 1].end;
        if (current.length >= MAX_WORDS_PER_PHRASE || gap > 0.3) {
          groups.push({ words: current, start: current[0].start, end: current[current.length - 1].end });
          current = [entry];
        } else {
          current.push(entry);
        }
      }
    });
    if (current.length > 0) {
      groups.push({ words: current, start: current[0].start, end: current[current.length - 1].end });
    }
    return groups;
  }, [wordTimestamps]);

  const visibleWords = useMemo(() => {
    const activePhrase = phrases.find(p => currentTime >= p.start - 0.1 && currentTime <= p.end + 0.2);
    return activePhrase ? activePhrase.words : [];
  }, [phrases, currentTime]);

  // 한국어 감지: CJK 문자 포함 여부
  const isCJK = useMemo(() => {
    return wordTimestamps.some(w => /[\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF]/.test(w.word));
  }, [wordTimestamps]);

  // captionY → paddingBottom 변환 (captionY=28→47%, captionY=38→42%, captionY=50→35%)
  const bottomPadding = `${Math.round(60 - captionY * 0.5)}%`;

  // 한국어: 카라오케 스타일 — 핵심 단어 노란색 + 팝업 애니메이션 (2025 트렌드)
  if (isCJK) {
    if (visibleWords.length === 0) return null;

    const cjkSize = Math.max(captionSize, 95);  // 95px (100만 쇼츠 기준 90~110px)
    const highlightColor = getEmotionColor(emotion);

    return (
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottomPadding }}>
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center',
          maxWidth: '92%',
          gap: '12px 14px',
          textAlign: 'center',
        }}>
          {visibleWords.map((w) => {
            const isActive = currentTime >= w.start && currentTime <= w.end;
            const isEmphasized = isActive && w.emphasis;

            // 카라오케: 현재 단어 = 노란색, 강조 단어 = 감정 색상, 나머지 = 흰색
            const color = isEmphasized
              ? highlightColor
              : isActive
                ? '#FFE600'  // 노란색 카라오케 하이라이트
                : '#FFFFFF';

            // 팝업 애니메이션: 현재 단어 살짝 커짐
            const scale = isActive ? 1.12 : 1;
            const opacity = currentTime >= w.start - 0.3 ? 1 : 0;

            return (
              <span
                key={w.index}
                style={{
                  fontFamily: "'Pretendard', 'Noto Sans KR', sans-serif",
                  fontWeight: 900,
                  fontSize: `${cjkSize}px`,
                  color: color,
                  textShadow: '3px 3px 0px #000, -3px -3px 0px #000, 3px -3px 0px #000, -3px 3px 0px #000, 0px 3px 0px #000, 0px -3px 0px #000, 3px 0px 0px #000, -3px 0px 0px #000',
                  WebkitTextStroke: '3px #000000',
                  paintOrder: 'stroke fill',
                  lineHeight: '1.3',
                  letterSpacing: '-1px',
                  display: 'inline-block',
                  transform: `scale(${scale})`,
                  opacity,
                  transition: 'transform 0.12s ease-out',
                }}
              >
                {w.word}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    );
  }

  // 영어/스페인어: 단어별 하이라이트 + 크기 강화
  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottomPadding }}>
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        width: '88%',
        gap: '14px 16px',
        textAlign: 'center',
        lineHeight: '1.4',
      }}>
        {visibleWords.map((w) => {
          const isActive = currentTime >= w.start && currentTime <= w.end;
          const hasPassed = currentTime > w.end;
          const isVisible = currentTime >= w.start - 0.5;

          if (!isVisible && !hasPassed && !isActive) return null;

          const isEmphasized = isActive && w.emphasis;
          const highlightColor = getEmotionColor(emotion);

          // 중복 제거: 상단 EMOTION_HIGHLIGHT_COLOR 재사용
          const emphasisColor = emotion && EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag] ? EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag] : '#FF4444';

          const color = isEmphasized
            ? emphasisColor
            : isActive
              ? highlightColor
              : 'rgba(255, 255, 255, 0.75)';

          const highlightGlow = `0px 2px 12px rgba(0, 0, 0, 0.9), 0px 0px 6px ${highlightColor}4D`;

          // emphasis glow uses emphasisColor for hex → rgba conversion
          const emphasisR = parseInt(emphasisColor.slice(1, 3), 16);
          const emphasisG = parseInt(emphasisColor.slice(3, 5), 16);
          const emphasisB = parseInt(emphasisColor.slice(5, 7), 16);

          const solidOutline = '4px 4px 0px #000, -4px -4px 0px #000, 4px -4px 0px #000, -4px 4px 0px #000, 0px 4px 0px #000, 0px -4px 0px #000, 4px 0px 0px #000, -4px 0px 0px #000, 0px 0px 8px rgba(0,0,0,0.7)';
          const textShadow = isEmphasized
            ? `${solidOutline}, 0px 0px 16px rgba(${emphasisR}, ${emphasisG}, ${emphasisB}, 0.7), 0px 0px 32px rgba(${emphasisR}, ${emphasisG}, ${emphasisB}, 0.3)`
            : isActive
              ? `${solidOutline}, 0px 0px 12px ${highlightColor}80, 0px 0px 24px ${highlightColor}40`
              : solidOutline;

          // 팝업 스케일: 활성 단어 1.12, 강조 단어 1.18
          const scale = isEmphasized ? 1.18 : isActive ? 1.1 : 1;

          // 영어/ES: 최소 100px 강제 (ES 전문가 권장 95~110px)
          const latinSize = Math.max(captionSize, 100);

          return (
            <span
              key={w.index}
              style={{
                fontFamily: "'Montserrat', 'Inter', sans-serif",
                fontWeight: 900,
                fontSize: `${latinSize}px`,
                color: color,
                textShadow: textShadow,
                WebkitTextStroke: '5px #000000',
                paintOrder: 'stroke fill',
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
