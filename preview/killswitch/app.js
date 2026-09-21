// app.js — UI 배선. 안전한 JSON 파싱 → 탐지 → 킬스위치 판정 → 렌더.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);

  const SAMPLES = {
    leak: {
      id: 1024,
      name: '홍길동',
      email: 'gildong@example.com',
      password: 'hunter2secret',
      profile: { phone: '010-1234-5678', is_admin: true, ssn: '900101-1234567' },
      session_token: 'eyJhbGciOiJIUzI1NiJ9.eyJ1IjoxMDI0fQ.abcDEF',
    },
    bola: [
      { order_id: 5001, owner_id: 11, total: 32000, card_number: '4111 1111 1111 1111' },
      { order_id: 5002, owner_id: 42, total: 8900, card_number: '5500005555555559' },
      { order_id: 5003, owner_id: 77, total: 15400, internal_note: '환불 요청' },
    ],
    clean: {
      id: 7,
      name: '이서연',
      nickname: 'seoyeon',
      avatar_url: 'https://cdn.example.com/a/7.png',
      joined_at: '2026-03-01',
    },
    bad: '{ "id": 1, "name": "깨진 JSON", }',
  };

  function safeParse(text) {
    const t = (text || '').trim();
    if (!t) return { ok: false, error: '내용이 비어 있습니다.' };
    try { return { ok: true, value: JSON.parse(t) }; }
    catch (e) { return { ok: false, error: 'JSON 형식이 올바르지 않습니다: ' + e.message }; }
  }

  function renderVerdict(v) {
    const el = $('verdict');
    el.className = 'verdict ' + v.status;
    let html = `<h3>${v.headline}</h3>`;
    if (v.message) html += `<div class="msg">${escapeHtml(v.message)}</div>`;
    if (v.rationale) html += `<p class="rationale">${escapeHtml(v.rationale)}</p>`;
    if (v.paperNote) html += `<p class="paperNote">📄 ${escapeHtml(v.paperNote)}</p>`;
    el.innerHTML = html;
    const code = window.KillSwitch.exitCode(v);
    $('exit').textContent = `CI/CD 관점 종료 코드: ${code} (${code === 1 ? '파이프라인 실패 → 배포 차단' : '통과'})`;
  }

  function renderFindings(findings) {
    const el = $('findings');
    if (!findings.length) { el.innerHTML = ''; return; }
    const rows = findings.map((f) => `
      <tr>
        <td><span class="sev ${f.severity}">${f.severity}</span></td>
        <td>${escapeHtml(f.rule)}</td>
        <td class="path">${escapeHtml(f.path || f.key || '')}</td>
        <td>${escapeHtml(f.detail || '')}</td>
        <td class="evidence">${escapeHtml(f.evidence || '')}</td>
      </tr>`).join('');
    el.innerHTML = `
      <h2 style="font-size:15px;margin:0 0 8px">탐지된 과다 노출 ${findings.length}건</h2>
      <table>
        <thead><tr><th>등급</th><th>규칙</th><th>경로</th><th>설명</th><th>근거(마스킹)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function run() {
    $('error').textContent = '';
    if (!window.Detectors || !window.KillSwitch) {
      $('error').textContent = '엔진 로드 실패: detectors.js / killswitch.js 를 확인하세요.';
      return;
    }
    const user = safeParse($('userJson').value);
    if (!user.ok) { $('error').textContent = user.error; $('output').hidden = true; return; }

    let options = {};
    const adminText = $('adminJson').value.trim();
    if (adminText) {
      const admin = safeParse(adminText);
      if (!admin.ok) { $('error').textContent = '관리자 응답 ' + admin.error; return; }
      options.adminPayload = admin.value;
    }

    let findings;
    try { findings = window.Detectors.scan(user.value, options) || []; }
    catch (e) { $('error').textContent = '진단 중 오류: ' + e.message; return; }

    const level = $('level').value;
    const v = window.KillSwitch.verdict(findings, level);
    renderVerdict(v);
    renderFindings(findings);
    $('output').hidden = false;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // 논문 근거 패널 채우기 (paper-data.js)
  function renderPaper() {
    const P = window.PAPER; if (!P) return;
    const levels = $('levels');
    levels.innerHTML = Object.entries(P.levels).map(([k, L]) => `
      <div class="level-row">
        <span class="tag">${k}</span>
        <span><b>${escapeHtml(L.name)}</b> — "${escapeHtml(L.instruction)}"<br>
          <span style="color:var(--muted)">${escapeHtml(L.finding)}</span></span>
      </div>`).join('');
    $('stats').innerHTML = P.key_stats.map((s) =>
      `<tr><td>${escapeHtml(s.label)}</td><td>${escapeHtml(s.value)}</td></tr>`).join('');
    $('antipattern').textContent =
      `안티패턴 회피: "${P.antipattern.phrase}" — ${P.antipattern.why}`;
  }

  // 이벤트
  document.addEventListener('DOMContentLoaded', () => {
    renderPaper();
    $('scanBtn').addEventListener('click', run);
    document.querySelectorAll('.samples button').forEach((b) => {
      b.addEventListener('click', () => {
        const s = SAMPLES[b.dataset.sample];
        $('userJson').value = typeof s === 'string' ? s : JSON.stringify(s, null, 2);
        $('adminJson').value = '';
        $('error').textContent = '';
      });
    });
  });
})();
