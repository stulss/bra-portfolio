// Shadow API / BOLA 진단 - 클라이언트 사이드 탐지 로직 (네트워크 호출 없음)

var CRITICAL_KEYS = [
  'password', 'passwd', 'pwd', 'secret', 'private_key', 'privatekey',
  'api_key', 'apikey', 'access_token', 'refresh_token', 'client_secret',
  'cvv', 'cvc'
];

var HIGH_SENSITIVE_KEYS = [
  'token', 'ssn', 'social_security', 'resident_registration',
  '주민등록번호', 'card_number', 'cardnumber', 'salt', 'otp',
  'session_id', 'sessionid'
];

var HIGH_OVERFETCH_KEYS = [
  'is_admin', 'isadmin', 'role', 'roles', 'permissions',
  'is_superuser', 'is_staff'
];

var MEDIUM_OVERFETCH_KEYS = [
  'internal', 'internal_note', 'deleted_at', 'is_deleted',
  'email_verified', 'password_reset_token', 'failed_login_count',
  'created_by', 'updated_by'
];

var OWNER_ID_KEYS = ['user_id', 'owner_id', 'userId', 'ownerId'];

var MAX_DEPTH = 64;

function maskValue(value) {
  var s = String(value);
  if (s.length <= 2) return '*'.repeat(s.length);
  return s.slice(0, 2) + '*'.repeat(s.length - 2);
}

function typeName(v) {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'array';
  return typeof v;
}

function valueEvidence(value) {
  if (typeof value === 'string') return "'" + maskValue(value) + "'";
  return '<' + typeName(value) + '>';
}

// 길이가 긴 패턴을 우선 매칭해서 'roles' vs 'role' 같은 중복 매치를 피한다.
function findFirstMatch(key, list) {
  var lower = String(key).toLowerCase();
  var sorted = list.slice().sort(function (a, b) { return b.length - a.length; });
  for (var i = 0; i < sorted.length; i++) {
    if (lower.indexOf(sorted[i].toLowerCase()) !== -1) return sorted[i];
  }
  return null;
}

function makeKeyFinding(rule, severity, path, key, value, detail) {
  return {
    rule: rule,
    severity: severity,
    path: path,
    key: key,
    detail: detail,
    evidence: key + '=' + valueEvidence(value)
  };
}

function checkKeyRules(key, value, path, findings) {
  if (findFirstMatch(key, CRITICAL_KEYS)) {
    findings.push(makeKeyFinding('sensitive_key', 'critical', path, key, value,
      "민감 키 '" + key + "'가 응답에 포함됨 — 화면에 안 보여도 JSON으로 노출."));
  } else if (findFirstMatch(key, HIGH_SENSITIVE_KEYS)) {
    findings.push(makeKeyFinding('sensitive_key', 'high', path, key, value,
      "민감 키 '" + key + "'가 응답에 포함됨 — 화면에 안 보여도 JSON으로 노출."));
  }

  if (findFirstMatch(key, HIGH_OVERFETCH_KEYS)) {
    findings.push(makeKeyFinding('overfetch_field', 'high', path, key, value,
      "과다응답: 관리자/내부 필드 '" + key + "'이(가) 일반 응답에 포함."));
  } else if (findFirstMatch(key, MEDIUM_OVERFETCH_KEYS)) {
    findings.push(makeKeyFinding('overfetch_field', 'medium', path, key, value,
      "과다응답: 내부 필드 '" + key + "'이(가) 일반 응답에 포함."));
  }
}

function luhnCheck(digits) {
  var sum = 0, alt = false;
  for (var i = digits.length - 1; i >= 0; i--) {
    var n = parseInt(digits[i], 10);
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n; alt = !alt;
  }
  return sum % 10 === 0;
}

function isCreditCard(v) {
  var digits = v.replace(/[\s-]/g, '');
  if (!/^\d{13,16}$/.test(digits)) return false;
  return luhnCheck(digits);
}

function isIPv4(v) {
  var m = v.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (!m) return false;
  for (var i = 1; i <= 4; i++) {
    var n = Number(m[i]);
    if (n < 0 || n > 255) return false;
  }
  return true;
}

var VALUE_PATTERNS = [
  { test: function (v) { return /\S+@\S+\.\S+/.test(v); }, severity: 'high', detail: '이메일 주소로 보이는 값이 응답에 포함됨.' },
  { test: function (v) { return /\d{6}-?\d{7}/.test(v); }, severity: 'high', detail: '주민등록번호 패턴의 값이 응답에 포함됨.' },
  { test: function (v) { return v.indexOf('eyJ') === 0 && (v.match(/\./g) || []).length >= 2; }, severity: 'high', detail: 'JWT 토큰으로 보이는 값이 응답에 포함됨.' },
  { test: isCreditCard, severity: 'high', detail: '신용카드 번호로 보이는 값이 응답에 포함됨(Luhn 검증 통과).' },
  { test: function (v) { return /01\d-?\d{3,4}-?\d{4}/.test(v); }, severity: 'medium', detail: '휴대폰 번호로 보이는 값이 응답에 포함됨.' },
  { test: isIPv4, severity: 'medium', detail: 'IP 주소로 보이는 값이 응답에 포함됨.' }
];

function checkValuePatterns(value, path, key, findings) {
  for (var i = 0; i < VALUE_PATTERNS.length; i++) {
    var p = VALUE_PATTERNS[i];
    if (p.test(value)) {
      findings.push({
        rule: 'sensitive_value',
        severity: p.severity,
        path: path,
        key: key,
        detail: p.detail,
        evidence: "'" + maskValue(value) + "'"
      });
    }
  }
}

// 서로 다른 소유자의 객체 배열이 한 응답에 노출되는지(BOLA 휴리스틱)
function checkBola(arr, path, findings) {
  if (arr.length < 3) return;
  var ownerValues = [];
  for (var i = 0; i < arr.length; i++) {
    var item = arr[i];
    if (typeof item !== 'object' || item === null || Array.isArray(item)) return;
    var found;
    for (var j = 0; j < OWNER_ID_KEYS.length; j++) {
      var k = OWNER_ID_KEYS[j];
      if (Object.prototype.hasOwnProperty.call(item, k)) { found = item[k]; break; }
    }
    if (found === undefined) return;
    ownerValues.push(found);
  }
  var uniq = new Set(ownerValues.map(String));
  if (uniq.size === ownerValues.length && uniq.size > 1) {
    findings.push({
      rule: 'bola_exposure',
      severity: 'high',
      path: path,
      key: '',
      detail: '여러 소유자의 객체가 한 응답에 노출 — 객체 수준 권한(BOLA) 점검 필요.',
      evidence: 'owner ids: ' + ownerValues.map(function (v) { return maskValue(String(v)); }).join(', ')
    });
  }
}

function walk(value, path, keyName, findings, depth) {
  if (depth > MAX_DEPTH) return;
  if (value === null || value === undefined) return;

  if (Array.isArray(value)) {
    checkBola(value, path, findings);
    for (var i = 0; i < value.length; i++) {
      var childPath = path === '' ? '[' + i + ']' : path + '[' + i + ']';
      walk(value[i], childPath, String(i), findings, depth + 1);
    }
    return;
  }

  if (typeof value === 'object') {
    for (var k in value) {
      if (!Object.prototype.hasOwnProperty.call(value, k)) continue;
      var v = value[k];
      var cp = path === '' ? k : path + '.' + k;
      checkKeyRules(k, v, cp, findings);
      walk(v, cp, k, findings, depth + 1);
    }
    return;
  }

  if (typeof value === 'string') {
    checkValuePatterns(value, path, keyName, findings);
  }
}

function scan(payload, options) {
  options = options || {};
  var findings = [];
  try {
    walk(payload, '', '', findings, 0);
  } catch (e) {
    return findings; // ponytail: 견고성 우선, 파싱 이상 시 빈 결과로 방어
  }

  if (options.adminPayload) {
    var overfetchHigh = findings.filter(function (f) {
      return f.rule === 'overfetch_field' && f.severity === 'high';
    });
    for (var i = 0; i < overfetchHigh.length; i++) {
      var f = overfetchHigh[i];
      findings.push({
        rule: 'structure_mismatch',
        severity: 'high',
        path: f.path,
        key: f.key,
        detail: "관리자 응답 구조가 일반 응답에 혼입 — 필드 '" + f.key + "'.",
        evidence: f.evidence
      });
    }
  }

  return findings;
}

if (typeof window !== 'undefined') window.Detectors = { scan: scan };
if (typeof module !== 'undefined') module.exports = { scan: scan };
