import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import React, { useMemo } from 'react';

type WordProps = {
  word: string;
  start: number;
  end: number;
};

// Emphasis detection: numbers, power words, impact vocabulary
// Based on Dual Coding Theory (Paivio 1986) — highlight ≤20% of words for optimal recall
const EMPHASIS_PATTERNS = /^(\d[\d,.]*[%배만억조x]?|미쳤|미침|소름|진짜|ㄹㅇ|대박|역대|최초|헐|insane|crazy|impossible|dead|never|every|million|billion|trillion|forever|nothing|destroy|vanish|disappear|survive|freeze|explode|entire|massive|infinite|absolute|unbelievable|incredible|shocking|terrifying)$/i;

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

// 감정별 강조색 — 포맷별 몰입감 강화
const EMOTION_HIGHLIGHT_COLOR: Record<EmotionTag, string> = {
  SHOCK:     '#FF3B30',  // 빨강 — 충격
  WONDER:    '#00D4FF',  // 하늘 — 경이
  TENSION:   '#FF9500',  // 주황 — 긴장
  REVEAL:    '#FFE600',  // 노랑 — 반전 (기본)
  URGENCY:   '#FF6B35',  // 오렌지레드 — 긴박
  DISBELIEF: '#FF3B30',  // 빨강 — 불신
  IDENTITY:  '#34C759',  // 초록 — 공감/정체성
  CALM:      '#FFFFFF',  // 흰색 — 차분
};
const DEFAULT_HIGHLIGHT = '#FFE600';

const getEmotionColor = (emotion?: string): string => {
  if (!emotion) return DEFAULT_HIGHLIGHT;
  return EMOTION_HIGHLIGHT_COLOR[emotion as EmotionTag] ?? DEFAULT_HIGHLIGHT;
};

const isEmphasisWord = (word: string): boolean => {
  const clean = word.replace(/[.,!?;:'"¿¡]/g, '').toLowerCase();
  if (EMPHASIS_PATTERNS.test(clean)) return true;
  if (/^\d/.test(clean)) return true;
  if (clean.length >= 7 && /^[a-z]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  if (clean.length >= 5 && /^[\uAC00-\uD7A3]+$/.test(clean)) return true;
  if (/^[\u30A0-\u30FF]{3,}$/.test(clean)) return true;
  if (clean.length >= 4 && /^[\u4E00-\u9FFF]+$/.test(clean)) return true;
  if (clean.length >= 8 && /^[a-zA-Z\u00C0-\u024F]+$/.test(clean) && !EN_STOPWORDS.has(clean)) return true;
  return false;
};

// 동적 폰트 크기 — 구(phrase) 총 글자 수 기반 자동 축소 (넘침 방지)
// 가용 너비: 1080 × 0.90 = 972px
// 실효 폭 = 1080 * 0.9 - padding(44px) - gap(12px per word gap) ≈ 912px
// KO: bold CJK 글자당 ~1.02em, EN: 글자당 ~0.6em
const EFFECTIVE_WIDTH = 912;
const calcCJKFontSize = (words: { word: string }[], base: number): number => {
  const totalChars = words.reduce((s, w) => s + w.word.replace(/\s/g, '').length, 0);
  const gapPx = Math.max(words.length - 1, 0) * 12; // word gap 12px
  const availWidth = EFFECTIVE_WIDTH - gapPx;
  const maxByWidth = Math.floor(availWidth / Math.max(totalChars * 1.02, 1));
  return Math.max(64, Math.min(base, maxByWidth));
};

const calcLatinFontSize = (words: { word: string }[], base: number): number => {
  const totalChars = words.reduce((s, w) => s + w.word.length + 1, 0); // +1 for space
  const maxByWidth = Math.floor(EFFECTIVE_WIDTH / Math.max(totalChars * 0.6, 1));
  return Math.max(52, Math.min(base, maxByWidth));
};

export const Captions: React.FC<{
  wordTimestamps: WordProps[];
  captionSize?: number;
  captionY?: number;
  emotion?: string;
  channel?: string;
}> = ({ wordTimestamps, captionSize = 48, captionY = 50, emotion, channel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // 구(phrase) 단위 그룹핑
  const phrases = useMemo(() => {
    const groups: { words: (WordProps & { index: number; emphasis: boolean })[]; start: number; end: number }[] = [];
    const hasCJK = wordTimestamps.some(w => /[\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF]/.test(w.word));
    // ES 단어가 길어서 3단어로 제한, EN은 4단어
    const isES = !hasCJK && wordTimestamps.some(w => /[áéíóúüñ¿¡]/i.test(w.word));
    const MAX_WORDS_PER_PHRASE = hasCJK ? 3 : isES ? 3 : 4;
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

  const visiblePhrase = useMemo(() => {
    return phrases.find(p => currentTime >= p.start - 0.1 && currentTime <= p.end + 0.1) ?? null;
  }, [phrases, currentTime]);

  const visibleWords = visiblePhrase?.words ?? [];

  // 한국어/CJK 감지
  const isCJK = useMemo(() => {
    return wordTimestamps.some(w => /[\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF]/.test(w.word));
  }, [wordTimestamps]);

  // EN 채널 감지 (wonderdrop)
  const isEN = !isCJK && (channel === 'wonderdrop' || (!channel && !wordTimestamps.some(w => /[áéíóúüñ]/i.test(w.word))));

  // captionY → paddingBottom (captionY=50→35%, captionY=38→42%, captionY=28→46%)
  const bottomPadding = `${Math.round(60 - captionY * 0.5)}%`;

  const highlightColor = getEmotionColor(emotion);

  if (visibleWords.length === 0) return null;

  // ── KO / CJK 자막 (배경박스 + 동적 크기) ──────────────────────────────
  if (isCJK) {
    const baseSize = Math.max(captionSize, 90);
    const fontSize = calcCJKFontSize(visibleWords, baseSize);

    return (
      <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottomPadding }}>
        {/* 배경박스 — 한국 상위 채널 필수, AI 이미지 위 가독성 확보 */}
        <div style={{
          backgroundColor: 'rgba(0, 0, 0, 0.68)',
          borderRadius: '10px',
          paddingTop: '14px',
          paddingBottom: '14px',
          paddingLeft: '22px',
          paddingRight: '22px',
          maxWidth: '90%',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '10px 12px',
          textAlign: 'center',
        }}>
          {visibleWords.map((w) => {
            const isActive = currentTime >= w.start && currentTime <= w.end;
            const isEmphasized = isActive && w.emphasis;
            const color = isActive ? highlightColor : '#FFFFFF';
            const opacity = 1; // 문장 단위로 동시 표시 (phrase visibility가 제어)
            // scale 제거 — flex 환경에서 레이아웃 박스 고정이라 옆 글자 침범 발생
            // 대신 강조 단어는 글로우 강화로 시각적 임팩트 전달
            const emphasisGlow = isEmphasized
              ? `, 0px 0px 16px ${highlightColor}, 0px 0px 32px ${highlightColor}80`
              : '';
            const baseStroke = '2px 2px 0px #000, -2px -2px 0px #000, 2px -2px 0px #000, -2px 2px 0px #000, 0px 2px 0px #000, 0px -2px 0px #000, 2px 0px 0px #000, -2px 0px 0px #000';

            return (
              <span
                key={w.index}
                style={{
                  fontFamily: "'Pretendard', 'Noto Sans KR', sans-serif",
                  fontWeight: 900,
                  fontSize: `${fontSize}px`,
                  color,
                  textShadow: `${baseStroke}${emphasisGlow}`,
                  WebkitTextStroke: '2px #000000',
                  paintOrder: 'stroke fill',
                  lineHeight: '1.3',
                  letterSpacing: '-0.5px',
                  display: 'inline-block',
                  opacity,
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

  // ── EN / ES 자막 (Hormozi 스타일, EN은 대문자) ────────────────────────
  const baseLatinSize = Math.max(captionSize, 88);
  const fontSize = calcLatinFontSize(visibleWords, baseLatinSize);

  const solidOutline = '4px 4px 0px #000, -4px -4px 0px #000, 4px -4px 0px #000, -4px 4px 0px #000, 0px 4px 0px #000, 0px -4px 0px #000, 4px 0px 0px #000, -4px 0px 0px #000, 0px 0px 10px rgba(0,0,0,0.8)';

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', paddingBottom: bottomPadding }}>
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        alignItems: 'center',
        width: '90%',
        gap: '12px 14px',
        textAlign: 'center',
        lineHeight: '1.35',
      }}>
        {visibleWords.map((w) => {
          const isActive = currentTime >= w.start && currentTime <= w.end;

          const isEmphasized = isActive && w.emphasis;
          const color = isActive ? highlightColor : 'rgba(255, 255, 255, 0.82)';
          // scale 제거 — 겹침 방지, 글로우 강화로 대체
          const textShadow = isActive
            ? isEmphasized
              ? `${solidOutline}, 0px 0px 14px ${highlightColor}, 0px 0px 28px ${highlightColor}80`
              : `${solidOutline}, 0px 0px 10px ${highlightColor}60`
            : solidOutline;

          // EN: 전부 대문자 (Hormozi 표준), ES: 원문 유지
          const displayWord = isEN ? w.word.toUpperCase() : w.word;

          return (
            <span
              key={w.index}
              style={{
                fontFamily: "'Montserrat', 'Inter', sans-serif",
                fontWeight: 900,
                fontSize: `${fontSize}px`,
                color,
                textShadow,
                WebkitTextStroke: '4px #000000',
                paintOrder: 'stroke fill',
                lineHeight: '1.3',
                display: 'inline-block',
              }}
            >
              {displayWord}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
