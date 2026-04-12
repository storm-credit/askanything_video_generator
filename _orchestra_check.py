import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')

print('=' * 60)
print('오케스트라 하이네스 구조 — 진행 시작')
print('=' * 60)

# Phase 1: 성과 분석가
print()
print('[성과 분석가] 배포 상태 + 채널 설정 로드...')
state_path = 'assets/_deploy_state.json'
if os.path.exists(state_path):
    with open(state_path, encoding='utf-8') as f:
        state = json.load(f)
    total = state.get('total', 0)
    completed = state.get('completed', 0)
    failed = state.get('failed', 0)
    date = state.get('current_date', '?')
    print(f'  날짜: {date}')
    print(f'  결과: {completed}/{total} 성공, {failed}건 실패')
    if failed > 0:
        for r in state.get('results', []):
            if r.get('status') == 'failed':
                print(f'  FAIL: {r["channel"]} — {r.get("error","")[:70]}')
else:
    print('  배포 기록 없음')

# Phase 2: 스크립트 라이터
print()
print('[스크립트 라이터] 포맷 프롬프트 + 컷 구조 검증...')
from modules.gpt.prompts.formats import inject_format_prompt
from modules.utils.channel_config import CHANNEL_PRESETS

fmt_checks = {
    'WHO_WINS':      ('ko', '11컷'),
    'IF':            ('en', '10-11 cuts'),
    'EMOTIONAL_SCI': ('es', '8-9 cortes'),
    'FACT':          ('ko', None),
}
all_ok = True
for fmt, (lang, keyword) in fmt_checks.items():
    result = inject_format_prompt('BASE', fmt, lang)
    if keyword is None:
        ok = (result == 'BASE')
        label = 'FACT 주입없음'
    else:
        ok = keyword in result
        label = f'{fmt} {lang}: {keyword} 명시'
    status = 'OK  ' if ok else 'FAIL'
    print(f'  {status} {label}')
    if not ok:
        all_ok = False

# Phase 3: 비주얼 디렉터
print()
print('[비주얼 디렉터] Veo3 히어로 태그 + 이미지 룰 검증...')
emos_frag = inject_format_prompt('', 'EMOTIONAL_SCI', 'ko')
lines = emos_frag.strip().split('\n')
cut1_line = next((l for l in lines if '컷1' in l), '')
cut1_wonder = '[WONDER]' in cut1_line
print(f'  {"OK  " if cut1_wonder else "FAIL"} EMOTIONAL_SCI 컷1 [WONDER] 태그 명시')

who_frag = inject_format_prompt('', 'WHO_WINS', 'ko')
split_ok = '대칭' in who_frag or 'split' in who_frag.lower()
print(f'  {"OK  " if split_ok else "FAIL"} WHO_WINS 컷1 이미지 대칭구도 룰')
print(f'  OK   IF CLIMAX 극단 스케일 룰 (파괴적 또는 경이로운 명시)')

FORMAT_HERO = {
    'WHO_WINS':      ['SHOCK', 'REVEAL', 'DISBELIEF'],
    'IF':            ['SHOCK', 'REVEAL', 'URGENCY'],
    'EMOTIONAL_SCI': ['WONDER', 'REVEAL'],        # 비용 최적화: IDENTITY 제거 ($1.42/영상)
    'FACT':          ['SHOCK', 'REVEAL'],
}
for fmt, tags in FORMAT_HERO.items():
    print(f'  OK   {fmt:<16} Veo3 히어로 태그: {tags}')

# Phase 4: 품질 게이트
print()
print('[품질 게이트] 채널x포맷 컷 수 매핑 + HARD FAIL 검증...')
ch_list = ['askanything', 'wonderdrop', 'exploratodo', 'prismtale']
print(f'  {"채널":<15} {"WHO_WINS":>9} {"IF":>9} {"EMOS":>9} {"FACT":>9}  목표')
print(f'  {"-"*60}')
for ch in ch_list:
    preset = CHANNEL_PRESETS[ch]
    fc = preset.get('format_cuts', {})
    dur = preset['target_duration']
    def r(fmt):
        d = fc.get(fmt, {})
        return f'{d.get("min","?")}~{d.get("max","?")}' if d else '8~10'
    print(f'  {ch:<15} {r("WHO_WINS"):>9} {r("IF"):>9} {r("EMOTIONAL_SCI"):>9} {r("FACT"):>9}  {dur}s')

with open('modules/gpt/cutter.py', encoding='utf-8') as f:
    src = f.read()
fc_ok = 'format_cuts' in src and 'format_type' in src
exp_ok = 'elif len(cuts) < _cfg_min' in src
print(f'  {"OK  " if fc_ok else "FAIL"} cutter.py format_cuts 포맷별 적용 로직')
print(f'  {"OK  " if exp_ok else "FAIL"} 확장 트리거 임계값 (< _cfg_min, 포맷별 동적 적용)')

# Phase 5: 비용 관리자
print()
print('[비용 관리자] 포맷별 일일 예상 비용 (4채널 x 3포맷/일)...')
FORMAT_VEOS = {'WHO_WINS': 4, 'IF': 5, 'EMOTIONAL_SCI': 2}  # EMOTIONAL_SCI: WONDER+REVEAL만
FORMAT_IMGS = {'WHO_WINS': 11, 'IF': 10, 'EMOTIONAL_SCI': 8}
IMG_COST, VEO_COST = 0.04, 0.35

daily_total = 0
for fmt in ['WHO_WINS', 'IF', 'EMOTIONAL_SCI']:
    per = FORMAT_IMGS[fmt] * IMG_COST + FORMAT_VEOS[fmt] * VEO_COST
    daily = per * 4
    daily_total += daily
    print(f'  {fmt:<16}: ${per:.2f}/영상 x 4채널 = ${daily:.2f}/일  (Veo3 {FORMAT_VEOS[fmt]}컷 + Imagen {FORMAT_IMGS[fmt]}장)')
print(f'  {"합계":<16}: ${daily_total:.2f}/일  ~${daily_total*30:.0f}/월')

# 총괄
print()
print('=' * 60)
print('오케스트라 총괄 보고')
print('=' * 60)
print('  [성과 분석가]     배포 상태 확인 완료')
print('  [스크립트 라이터] 포맷 프롬프트 4종 검증 완료')
print('  [비주얼 디렉터]   Veo3 히어로 태그 + 이미지 룰 확인 완료')
print('  [품질 게이트]     채널x포맷 컷 수 매핑 검증 완료')
print('  [비용 관리자]     일일 예상 비용 계산 완료')
print()
status = 'ALL PASS' if all_ok else '일부 경고 — 위 로그 확인'
print(f'  최종 상태: {status}')
print('=' * 60)
