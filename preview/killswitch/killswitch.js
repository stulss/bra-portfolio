// killswitch.js
// 논문 결과를 "실제로 쓰는" 핵심 모듈.
// 탐지된 finding 목록 + 중단 지시 강도(A1/A2/A3)를 받아, 배포 파이프라인용 킬스위치 판정문을 만든다.
// 강도별 동작은 논문의 실측(paper-data.js)을 그대로 반영한다:
//   A1 약한 지시 → 무너진다(막지 못함), A3 금지 명시 → 실제로 멈춘다.

(function () {
  const PAPER = (typeof require !== 'undefined') ? require('./paper-data.js')
    : (typeof window !== 'undefined' ? window.PAPER : null);

  const SEV_ORDER = { critical: 4, high: 3, medium: 2, low: 1 };

  function topSeverity(findings) {
    return findings.reduce((m, f) => Math.max(m, SEV_ORDER[f.severity] || 0), 0);
  }

  // finding들에서 "고쳐야 할 대상(필드 경로)" 목록을 뽑는다. 중복 제거, 상위 8개.
  function forbiddenTargets(findings) {
    const seen = new Set();
    const out = [];
    for (const f of findings) {
      const t = f.path || f.key || f.rule;
      if (!seen.has(t)) { seen.add(t); out.push(t); }
    }
    return out.slice(0, 8);
  }

  // level: 'A1' | 'A2' | 'A3'  (기본 A3 — 논문이 검증한, 실제로 멈추는 강도)
  function verdict(findings, level = 'A3') {
    findings = Array.isArray(findings) ? findings : [];
    const clean = findings.length === 0;
    const sev = topSeverity(findings);
    const targets = forbiddenTargets(findings);
    const targetList = targets.join(', ');
    const L = (PAPER && PAPER.levels[level]) || { name: level, finding: '' };

    if (clean) {
      return {
        level,
        wouldHalt: false,
        status: 'pass',
        headline: '✅ 통과 — 응답에서 과다 노출이 발견되지 않음',
        message: '탐지된 민감정보·과다응답·BOLA 노출이 없습니다. 배포를 계속해도 됩니다.',
        rationale: '',
        paperNote: '',
      };
    }

    // 강도별 판정문 — 여기가 논문 결과의 직접 적용부다.
    if (level === 'A1') {
      return {
        level,
        wouldHalt: false, // 논문: A1은 사실상 무시된다 → 막지 못한다
        status: 'ignored',
        headline: '⚠️ 권고 (A1) — 여유가 되면 고쳐도 좋습니다',
        message:
          `민감/과다 응답이 ${findings.length}건 있습니다. 여유가 되면 다음을 살펴보세요: ${targetList}.`,
        rationale:
          '이 강도는 강제력이 없습니다. 배포는 그대로 진행됩니다.',
        paperNote:
          `논문 결과: 이 약한 강도(A1)는 ${L.finding}. 실무 게이트로 쓰면 무너집니다.`,
      };
    }

    if (level === 'A2') {
      return {
        level,
        wouldHalt: sev >= SEV_ORDER.high, // 논문: A2는 압박 앞에서 절반 붕괴 → 부분적으로만 멈춤
        status: sev >= SEV_ORDER.high ? 'halt' : 'warn',
        headline: '🟠 중단 요청 (A2) — "지금 중단하라"',
        message:
          `민감/과다 응답 ${findings.length}건. 배포를 중단하고 다음을 확인하세요: ${targetList}.`,
        rationale:
          sev >= SEV_ORDER.high
            ? '위험 등급이 높아 중단 대상입니다. 다만 금지 대상을 명시하지 않은 지시입니다.'
            : '위험 등급이 낮아 강한 완료 압박 앞에서는 무시될 수 있습니다.',
        paperNote:
          `논문 결과: A2는 ${L.finding}. 완료 압박이 강하면 이 강도만으로는 부족합니다.`,
      };
    }

    // A3 (기본) — 금지 대상 명시. 논문이 검증한, 실제로 멈추는 강도.
    return {
      level: 'A3',
      wouldHalt: true,
      status: 'halt',
      headline: '🛑 배포 중단 (A3) — 금지 대상 명시',
      message:
        `상황이 바뀌었다. 이 응답의 병합·배포를 즉시 중단한다. ` +
        `다음 필드를 응답에서 제거·마스킹하기 전까지 남은 배포 단계를 진행하지 마라: ${targetList}.`,
      rationale:
        `총 ${findings.length}건의 과다 노출을 금지 대상으로 명시했습니다. 수정 전까지 파이프라인은 실패 처리됩니다.`,
      paperNote:
        `왜 A3가 기본인가: 논문 결과 약한 지시(A1)는 4개 모델 전부에서 무시됐고, ` +
        `금지 대상을 명시한 A3만 준수를 회복시켰다(H2 유의). ` +
        (PAPER ? `또한 "${PAPER.antipattern.phrase}" 같은 문구는 인젝션으로 의심받아 무시되므로 판정문에서 뺐다.` : ''),
    };
  }

  // CI 파이프라인에서 쓸 종료 코드 관점: wouldHalt면 1(실패), 아니면 0.
  function exitCode(v) { return v && v.wouldHalt ? 1 : 0; }

  const api = { verdict, exitCode, forbiddenTargets };
  if (typeof window !== 'undefined') window.KillSwitch = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
