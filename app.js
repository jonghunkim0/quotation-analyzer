/* ============================================================
 * 원가구성 비교 분석 도구 - 핵심 로직 (브라우저용)
 * Python 버전의 로직을 JavaScript로 이식
 * ============================================================ */

// ─── 비용 분류 (13개) ────────────────────────────────────────
const COST_CATEGORIES = [
  "기구 재료비", "전장·제어 재료비", "사급품", "구매품",
  "기구설계 인건비", "제어설계 인건비", "조립 인건비",
  "셋업 인건비(기구)", "셋업 인건비(제어)", "셋업 인건비(전장)", "양산대응 인건비",
  "경비", "마진", "미분류",
];

const COST_GROUPS = {
  "재료비": ["기구 재료비", "전장·제어 재료비", "구매품", "사급품"],
  "인건비": ["기구설계 인건비", "제어설계 인건비", "조립 인건비",
             "셋업 인건비(기구)", "셋업 인건비(제어)", "셋업 인건비(전장)", "양산대응 인건비", "경비"],
  "기업이윤": ["마진"],
  "기타": ["미분류"],
};

const GROUP_NAMES = ["재료비", "인건비", "기업이윤", "기타"];

const GROUP_COLORS = {
  "재료비": "#3B82F6",
  "인건비": "#F97316",
  "기업이윤": "#EF4444",
  "기타": "#6B7280",
};

const DEFAULT_STACK_ORDER = [
  "기구 재료비", "전장·제어 재료비", "구매품", "사급품",
  "기구설계 인건비", "제어설계 인건비", "조립 인건비",
  "셋업 인건비(기구)", "셋업 인건비(제어)", "셋업 인건비(전장)", "양산대응 인건비",
  "경비", "마진", "미분류",
];

const CATEGORY_COLORS = {
  "기구 재료비": "#4B5563", "전장·제어 재료비": "#9CA3AF",
  "구매품": "#8B5CF6", "사급품": "#0D9488",
  "기구설계 인건비": "#F97316", "제어설계 인건비": "#C2410C",
  "조립 인건비": "#FACC15", "셋업 인건비(기구)": "#86EFAC",
  "셋업 인건비(제어)": "#22C55E", "셋업 인건비(전장)": "#15803D",
  "양산대응 인건비": "#0EA5E9",
  "경비": "#64748B", "마진": "#EF4444", "미분류": "#1F2937",
};

const DEFAULT_SCENARIOS = ["견적가", "구매 목표가", "개발 검토가"];

const SUPPLY_OPTIONS = [
  "사급품을 재료비율에 포함",
  "사급품을 재료비율에서 제외",
  "사급품을 총원가에 포함",
  "사급품을 총원가에서 제외",
  "사급품을 금액 없이 참고 항목으로만 표시",
];

const AMOUNT_UNITS = { "원": 1, "천원": 1000, "백만원": 1000000, "억원": 100000000 };

// ─── 열 이름 매핑 ────────────────────────────────────────────
const COLUMN_ALIASES = {
  "품명": ["품명", "품목", "품목명", "항목", "item", "description", "내역", "part name", "part", "명세", "item name", "item description"],
  "사양": ["사양", "규격", "spec", "specification", "상세내용", "model", "모델", "재질", "material", "size", "크기", "치수", "dimension"],
  "수량": ["수량", "qty", "quantity", "개수", "count"],
  "단가": ["단가", "unit price", "unit", "단가(원)", "unit cost", "unit price(원)"],
  "금액": ["금액", "amount", "price", "공급가액", "total", "합계", "금액(원)", "total amount", "amount(원)", "합계금액"],
  "비고": ["비고", "remark", "note", "remarks", "메모", "comment", "memo", "설명"],
  "구분": ["구분", "category", "type", "비용구분", "분류", "항목구분", "cost category"],
  "업체명": ["업체명", "공급사", "vendor", "supplier", "제조사", "maker", "brand", "공급업체", "vendor name"],
  "부가세": ["부가세", "vat", "tax", "세금", "부가가치세"],
};

const TOTAL_ROW_KEYWORDS = [
  "합계", "총계", "소계", "total", "grand total", "subtotal",
  "부가세", "vat", "세금", "tax", "최종합계", "final total",
];

// ─── 분류 키워드 규칙 ────────────────────────────────────────
const CLASSIFICATION_RULES = {
  "사급품": ["사급품", "사급", "고객사 지급", "고객 지급", "지급자재", "고객 제공",
             "무상 지급", "customer supply", "customer supplied", "consigned",
             "free issue", "고객부품", "고객제공"],
  "구매품": ["구매품", "구매 part", "구매파트", "외주 구매", "상용품", "표준 구매",
             "vendor item", "commercial part", "buy part", "purchased item",
             "외부 조달",
             // 기계 표준 구매 부품 (모터·실린더·로봇 등 장비에 들어가는 구매 부품)
             "모터", "서보", "실린더", "로봇", "lm가이드", "lm 가이드", "볼스크류", "볼 스크류",
             "베어링", "기어", "커플링", "벨트", "풀리", "스프링",
             // 전장·제어 표준 구매 부품
             "plc", "hmi", "센서", "인버터", "차단기", "릴레이", "스위치", "터미널",
             "커넥터", "전원공급기", "psu", "컨택터", "마그네틱", "피더",
             "브레이커", "조명", "램프", "버튼", "코일", "트랜스", "제어 부품",
             // English
             "motor", "servo", "cylinder", "robot", "lm guide", "lmguid", "ball screw", "ballscrew",
             "bearing", "gear", "coupling", "belt", "pulley", "spring",
             "plc", "hmi", "sensor", "inverter", "breaker", "relay", "switch",
             "terminal", "connector", "power supply", "contactor", "magnetic", "feeder",
             "lamp", "button", "coil", "transformer"],
  "기구 재료비": ["프레임", "플레이트", "플라이트", "플레이트재", "브라켓", "브래킷",
             "블라켓", "블랙켓", "가공품", "알루미늄", "프로파일",
             "볼트", "너트", "기계 제작", "스페이서", "샤프트", "플랜지", "지지대", "베이스", "커버",
             "하우징", "케이스", "스틸", "강판",
             "frame", "plate", "bracket", "aluminum", "aluminium", "profile",
             "bolt", "nut", "spacer", "shaft", "flange", "base", "cover", "housing", "case", "steel", "machined",
             "mechanical part", "mechanical material",
             // 약자 (단어 경계 매칭: matchKw)
             "plt", "blk", "bkt"],
  "전장·제어 재료비": ["판넬", "전선", "케이블", "전장품",
             "panel", "wire", "cable", "electrical part", "electrical material"],
  "기구설계 인건비": ["기구설계", "기계설계", "구조설계", "cad", "3d 설계", "2d 도면",
             "상세설계", "도면 작성", "기구 설계", "기계 설계", "설계 인건",
             "mechanical design", "mechanical engineering", "structural design",
             "mechanical drawing"],
  "제어설계 인건비": ["제어설계", "plc 프로그램", "hmi 프로그램", "소프트웨어 설계",
             "전장설계", "회로설계", "제어 로직", "프로그램 개발", "제어 설계",
             "sw 설계", "프로그래밍",
             "control design", "control engineering", "plc programming",
             "hmi programming", "software design", "circuit design", "programming"],
  "조립 인건비": ["조립", "기계조립", "기구조립", "장비조립", "제작 인건비",
             "조립 공수", "조립 인건", "설치 인건",
             "assembly", "assemble", "installation labor"],
  "셋업 인건비(기구)": ["기구 셋업", "기계 셋업", "기구 조정", "얼라인", "정밀 조정",
             "기구 튜닝", "레벨링", "기구 세팅", "정렬", "셋업기구엔지니어",
             "mechanical setup", "mechanical alignment", "align", "leveling",
             "mechanical tuning"],
  "셋업 인건비(제어)": ["프로그램 셋업", "제어 셋업", "시운전", "디버깅", "제어 튜닝",
             "plc 셋업", "hmi 셋업", "제어 세팅", "동작 테스트", "셋업제어엔지니어",
             "control setup", "commissioning", "test run", "debugging",
             "control tuning", "operation test"],
  "셋업 인건비(전장)": ["현장 배선", "전장 셋업", "판넬 설치", "판넬 결선",
             "케이블 포설", "입출력 확인", "전장 공사", "배선", "결선", "셋업전장엔지니어",
             "field wiring", "electrical setup", "panel installation",
             "cable laying", "wiring", "electrical work"],
  "양산대응 인건비": ["양산대응", "양산 대응", "양산인건", "양산 인건",
             "mass production", "mp response"],
  "경비": ["운송비", "출장비", "숙박비", "교통비", "포장비", "안전관리비",
             "일반관리비", "보험료", "설치 경비", "현장 경비", "배송비", "운반비",
             "관리비", "경비",
             "transportation", "delivery", "shipping", "travel", "accommodation",
             "packaging", "insurance", "overhead", "expense"],
  "마진": ["마진", "이윤", "profit", "margin", "영업이익", "이익률", "이익", "수익"],
};

const PRIORITY_CATEGORIES = ["사급품", "구매품"];

// 규칙 1: 항목 내용에 명시된 분류 정보(사급/구매품/가공품 등) → 최우선
// (가공품은 독립 카테고리가 아니라 기구 재료비로 분류)
const EXPLICIT_CLASSIFICATION = {
  "사급품": ["사급품", "사급"],
  "구매품": ["구매품"],
  "기구 재료비": ["가공품"],
};

// 규칙 2: 섹션 헤더("구매품 소개", "가공품 소개" 등) → 섹션 내 항목 통일 분류
const SECTION_CLASSIFICATION = {
  "구매품": ["구매품"],
  "기구 재료비": ["가공품"],
};

// 규칙 3: 품명에 플레이트/브라켓 계열이 있으면 구매품 우선 매칭을 건너뜀
// (예: "Z-ROBOT-PLATE-1"의 robot, "SENSOR-BKT-1"의 sensor가 구매품으로 오분류하는 것 방지)
const MECH_PART_GUARD_KWS = [
  "플레이트", "플라이트", "플레이트재", "브라켓", "브래킷", "블라켓", "블랙켓",
  "plt", "blk", "bkt", "plate", "bracket",
];

// 짧은 영문 약자(plt/blk/bkt 등)는 단어 경계로 매칭해 오탐 방지.
// 품명 표기 관례상 _ 와 - 도 단어 경계로 취급 (예: ROBOT_BASE_PLATE → plate 매칭)
function matchKw(kw, normText) {
  const nkw = normalizeText(kw);
  if (!nkw) return false;
  if (/^[a-z0-9]+$/.test(nkw) && nkw.length <= 5) {
    const esc = nkw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp("(?<![a-z0-9])" + esc + "(?![a-z0-9])").test(normText);
  }
  return normText.includes(nkw);
}

// ─── 유틸리티 ────────────────────────────────────────────────
function normalizeText(text) {
  if (!text) return "";
  return String(text).replace(/\s+/g, "").toLowerCase();
}

function parseAmount(value) {
  if (value === null || value === undefined) return 0;
  if (typeof value === "number") return value;
  let s = String(value).trim();
  if (!s || ["-", "--", "N/A", "n/a", "없음"].includes(s)) return 0;

  let negative = false;
  if (s.startsWith("(") && s.endsWith(")")) { negative = true; s = s.slice(1, -1); }
  else if (s.startsWith("(-") && s.endsWith(")")) { negative = true; s = s.slice(2, -1); }

  s = s.replace(/[₩$€¥,，\s]/g, "");
  if (s.startsWith("-")) { negative = true; s = s.slice(1); }

  const m = s.match(/[\d.]+/);
  if (!m) return 0;
  const result = parseFloat(m[0]);
  if (isNaN(result)) return 0;
  return negative ? -result : result;
}

function formatAmount(amount, unit, decimals) {
  const divisor = AMOUNT_UNITS[unit] || 1;
  const suffix = unit === "억원" ? "억" : unit;
  const v = amount / divisor;
  if (decimals === 0) return v.toLocaleString("ko-KR", { maximumFractionDigits: 0 }) + suffix;
  return v.toLocaleString("ko-KR", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + suffix;
}

function autoDetectUnit(maxAmount) {
  if (maxAmount >= 1000000000) return "억원";
  if (maxAmount >= 10000000) return "백만원";
  if (maxAmount >= 100000) return "천원";
  return "원";
}

function safeDivide(a, b, def) { return b === 0 ? (def || 0) : a / b; }

function matchColumn(header, aliases) {
  const norm = normalizeText(header);
  if (!norm) return false;
  for (const alias of aliases) {
    const na = normalizeText(alias);
    if (!na) continue;
    if (norm === na) return true;
    if (norm.length <= 2) continue; // 짧은 헤더는 부분 일치로 오매칭 방지 (예: "No" ≠ "note")
    if (norm.includes(na) || na.includes(norm)) return true;
  }
  return false;
}

function isTotalRow(text) {
  const norm = normalizeText(text);
  for (const kw of TOTAL_ROW_KEYWORDS) {
    if (norm.includes(normalizeText(kw))) return true;
  }
  return false;
}

// ─── 유사 항목 전파 (문맥 기반 분류) ─────────────────────────────────────────
// 협력사/담당자마다 표현 방식이 달라 키워드로 못 잡은 미분류 항목을,
// 같은 파일에서 이미 분류된 항목과 문자 2-그램 Dice 유사도로 비교해 전파한다.
// 섹션(hint)이 같은 매칭은 보너스 → "양산대기 기구" ↔ "양산대응 기구" 같은 오타/약어 대응
function _bigrams(s) {
  const set = new Set();
  for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
  return set;
}
function _dice(a, b) {
  const A = _bigrams(a), B = _bigrams(b);
  if (!A.size || !B.size) return 0;
  let inter = 0;
  for (const g of A) if (B.has(g)) inter++;
  return (2 * inter) / (A.size + B.size);
}
function propagateSimilar(items) {
  let count = 0;
  const classified = items.filter(i => i.final_category && i.final_category !== "미분류");
  for (const it of items) {
    if (it.final_category !== "미분류") continue;
    const text = normalizeText(`${it.name} ${it.spec || ""} ${it.category_hint || ""}`);
    let best = null, bestScore = 0;
    for (const ref of classified) {
      const refText = normalizeText(`${ref.name} ${ref.spec || ""} ${ref.category_hint || ""}`);
      let score = _dice(text, refText);
      if (it.category_hint && it.category_hint === ref.category_hint) score += 0.15; // 섹션 동일 보너스
      if (score > bestScore) { bestScore = score; best = ref; }
    }
    if (best && bestScore >= 0.6) {
      it.auto_category = best.final_category;
      it.final_category = best.final_category;
      it.confidence = 70;
      it.reason = `유사 항목 전파: '${best.name}'`;
      count++;
    }
  }
  return count;
}

// ─── 자동 분류 ───────────────────────────────────────────────
function classifyItem(item, userRules) {
  const texts = [item.name, item.spec, item.remark, item.category_hint].filter(Boolean);
  const combined = texts.join(" ");
  const normCombined = normalizeText(combined);

  if (!normCombined) {
    return { category: "미분류", confidence: 0, keywords: [], reason: "품명, 사양, 비고가 모두 비어 있습니다." };
  }

  // 1) 사용자 규칙 우선
  for (const [kw, cat] of Object.entries(userRules || {})) {
    if (normCombined.includes(normalizeText(kw))) {
      return { category: cat, confidence: 95, keywords: [kw], reason: `사용자 규칙 '${kw}' 적용` };
    }
  }

  // 1-1) 규칙 1: 항목 내용에 명시된 분류 정보(사급/구매품/가공품) → 최우선
  for (const [cat, kws] of Object.entries(EXPLICIT_CLASSIFICATION)) {
    const matched = kws.filter(kw => matchKw(kw, normCombined));
    if (matched.length) {
      return { category: cat, confidence: 95, keywords: matched, reason: `항목 내용에 '${matched.join(", ")}' 명시 → ${cat}으로 분류` };
    }
  }

  // 1-2) 규칙 2: 섹션 헤더("구매품 소개", "가공품 소개" 등) → 섹션 내 항목 통일 분류
  const normHint0 = normalizeText(item.category_hint);
  if (normHint0) {
    for (const [cat, kws] of Object.entries(SECTION_CLASSIFICATION)) {
      if (kws.some(kw => matchKw(kw, normHint0))) {
        return { category: cat, confidence: 85, keywords: [item.category_hint], reason: `섹션 '${item.category_hint}' 기준 → ${cat}으로 통일 분류` };
      }
    }
  }

  // 2) 우선순위 (사급품/구매품)
  //    단, 품명/비고에 인건비 성격(설계·조립·셋업·인건 등)이 있으면
  //    사양의 부품 키워드(예: "제어설계 | PLC/HMI")가 구매품으로 오분류하지 않도록
  //    구매품 우선 매칭만 건너뜀 (사급품은 명시적 신호이므로 그대로 적용)
  const laborName = normalizeText(`${item.name || ""} ${item.remark || ""}`);
  const isLaborItem = /설계|조립|셋업|세팅|인건|시운전|정렬|얼라인|튜닝|레벨링|결선|배선|포설|설치|도면|프로그래밍|개발|테스트|관리비|운송|출장|숙박|배송|포장|보험/.test(laborName);
  for (const pCat of PRIORITY_CATEGORIES) {
    if (pCat === "구매품" && isLaborItem) continue;
    const kws = CLASSIFICATION_RULES[pCat] || [];
    const matched = kws.filter(kw => matchKw(kw, normCombined));
    if (matched.length) {
      const confidence = Math.min(95, 80 + matched.length * 5);
      return { category: pCat, confidence, keywords: matched, reason: `'${matched.join(", ")}' 키워드로 ${pCat}으로 분류` };
    }
  }

  // 3) 일반 분류 매칭
  let bestCategory = "미분류", bestScore = 0, bestKeywords = [], bestReason = "";
  for (const category of COST_CATEGORIES) {
    if (category === "미분류") continue;
    const kws = CLASSIFICATION_RULES[category] || [];
    const matched = kws.filter(kw => matchKw(kw, normCombined));
    if (matched.length) {
      let score = matched.length * 10;
      const normName = normalizeText(item.name);
      if (matched.some(kw => matchKw(kw, normName))) score += 15;
      const normHint = normalizeText(item.category_hint);
      if (matched.some(kw => matchKw(kw, normHint))) score += 10;
      // 설계/design 키워드가 품명에 있으면 해당 인건비 분류 우선 (예: "Control Design PLC/HMI" → 제어설계)
      if (matched.some(kw => /design|설계/.test(kw) && matchKw(kw, normName))) score += 25;
      if (score > bestScore) {
        bestScore = score;
        bestCategory = category;
        bestKeywords = matched;
        bestReason = `'${matched.join(", ")}' 키워드로 ${category}으로 분류`;
      }
    }
  }

  // 4) 섹션 기반 폴백: 키워드 매칭 실패 시 엑셀의 부분 구분 이름으로 분류
  //    번호([1], [2]...)에 의존하지 않고 섹션 이름의 키워드로 판단 → 협력사별 양식 차이 대응
  if (bestCategory === "미분류") {
    const hint = normalizeText(item.category_hint);
    // 양산대응 섹션 → 양산대응 인건비 (기구/전장 등 다른 폴백보다 우선)
    if (/양산/.test(hint)) {
      return { category: "양산대응 인건비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
    }
    const hasMech = /기구|기계|구조|mechanical|structure/.test(hint);
    const hasElec = /전장|제어|전기|electrical|electric|control/.test(hint);
    if (hasMech && !hasElec) {
      return { category: "기구 재료비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
    }
    if (hasElec && !hasMech) {
      return { category: "전장·제어 재료비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
    }
    if (/인건|인력|labor|manpower/.test(hint)) {
      if (/설계|design/.test(hint)) {
        if (hasMech) return { category: "기구설계 인건비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
        if (hasElec) return { category: "제어설계 인건비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
      }
      if (/조립|assembly/.test(hint)) {
        return { category: "조립 인건비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
      }
      if (/셋업|setup/.test(hint)) {
        if (hasMech) return { category: "셋업 인건비(기구)", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
        if (/전장|배선|wiring/.test(hint)) return { category: "셋업 인건비(전장)", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
        if (hasElec) return { category: "셋업 인건비(제어)", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
      }
    }
    if (/경비|관리비|운송|배송|포장|expense|overhead|transport|delivery|packaging/.test(hint)) {
      return { category: "경비", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
    }
    if (/마진|이윤|profit|margin/.test(hint)) {
      return { category: "마진", confidence: 45, keywords: [], reason: `키워드 매칭 실패 → 섹션 '${item.category_hint}' 기준 분류` };
    }
    return { category: "미분류", confidence: Math.min(40, bestScore), keywords: [], reason: "분류 근거가 부족합니다. 사용자 확인이 필요합니다." };
  }

  const normName = normalizeText(item.name);
  const nameMatch = bestKeywords.some(kw => matchKw(kw, normName));
  const nKw = bestKeywords.length;
  let confidence;
  if (nameMatch && nKw >= 1) confidence = Math.min(95, 90 + nKw * 2);
  else if (nKw >= 2) confidence = Math.min(89, 75 + nKw * 3);
  else if (nKw === 1) confidence = 75;
  else confidence = 55;

  // 여러 분류 동시 해당
  const multiMatches = COST_CATEGORIES.filter(c => {
    if (c === "미분류") return false;
    return (CLASSIFICATION_RULES[c] || []).some(kw => matchKw(kw, normCombined));
  });
  if (multiMatches.length > 1) {
    confidence = Math.max(50, confidence - 15);
    bestReason += ` (참고: ${multiMatches.join(", ")}에도 해당)`;
  }

  return { category: bestCategory, confidence, keywords: bestKeywords, reason: bestReason };
}

// ─── 집계 ────────────────────────────────────────────────────
function aggregateScenario(name, items, supplyOption) {
  const categoryTotals = {};
  COST_CATEGORIES.forEach(c => categoryTotals[c] = 0);
  items.forEach(it => {
    if (it.is_tax || it.is_total_row) return;
    const cat = categoryTotals[it.final_category] !== undefined ? it.final_category : "미분류";
    categoryTotals[cat] += it.amount;
  });

  const supplyTotal = categoryTotals["사급품"];
  const purchaseTotal = categoryTotals["구매품"];

  let supplyInMaterial = ["사급품을 재료비율에 포함", "사급품을 총원가에 포함"].includes(supplyOption);
  let supplyInTotal = ["사급품을 재료비율에 포함", "사급품을 총원가에 포함", "사급품을 재료비율에서 제외"].includes(supplyOption);
  if (supplyOption === "사급품을 금액 없이 참고 항목으로만 표시") { supplyInMaterial = false; supplyInTotal = false; }

  let materialTotal = COST_GROUPS["재료비"].filter(c => c !== "사급품").reduce((s, c) => s + categoryTotals[c], 0);
  if (supplyInMaterial) materialTotal += supplyTotal;

  // 인건비 그룹에 경비 포함 (COST_GROUPS["인건비"]에 "경비" 포함)
  const laborTotal = COST_GROUPS["인건비"].reduce((s, c) => s + categoryTotals[c], 0);
  const expenseTotal = categoryTotals["경비"]; // 참고용 (laborTotal에 이미 포함)
  const marginTotal = categoryTotals["마진"];
  const unclassifiedTotal = categoryTotals["미분류"];

  const analysisCost = materialTotal + laborTotal; // 경비 이미 laborTotal에 포함
  const totalAmount = analysisCost + marginTotal + unclassifiedTotal;

  const baseTotal = totalAmount !== 0 ? totalAmount : 1;
  const materialRate = safeDivide(materialTotal, baseTotal) * 100;
  const materialWithSupply = materialTotal + (supplyInMaterial ? 0 : supplyTotal);
  const materialRateWithSupply = safeDivide(materialWithSupply, baseTotal) * 100;

  const categoryRatios = {};
  COST_CATEGORIES.forEach(c => categoryRatios[c] = safeDivide(categoryTotals[c], baseTotal) * 100);

  return {
    name, items, categoryTotals, categoryRatios,
    totalAmount, analysisCost, materialTotal, laborTotal,
    expenseTotal, marginTotal, supplyTotal, purchaseTotal,
    materialRate, materialRateWithSupply,
  };
}

// 1차 그룹별 합계 (재료비/인건비/기업이윤/기타)
function groupTotals(categoryTotals) {
  const result = {};
  GROUP_NAMES.forEach(g => {
    result[g] = COST_GROUPS[g].reduce((s, c) => s + (categoryTotals[c] || 0), 0);
  });
  return result;
}

function computeDeltas(scenarios) {
  const results = [];
  for (let i = 1; i < scenarios.length; i++) {
    const prev = scenarios[i - 1], curr = scenarios[i];
    const pair = COST_CATEGORIES.map(cat => {
      const pv = prev.categoryTotals[cat] || 0;
      const cv = curr.categoryTotals[cat] || 0;
      const d = cv - pv;
      return { category: cat, from: prev.name, to: curr.name, deltaAmount: d, deltaRate: safeDivide(d, Math.abs(pv)) * 100 };
    });
    results.push(pair);
  }
  return results;
}

// ─── Excel 파싱 (SheetJS) ────────────────────────────────────
function parseExcelSheet(rows, filename, sheetName, scenario, sumRows) {
  // rows: 2D array (header=None equivalent)
  // sumRows: Set(0-based 행 인덱스) — 다른 행을 참조하는 합산 수식 행 (분류 제외)
  // 헤더 행 탐지
  let headerIdx = -1, bestScore = 0;
  const maxScan = Math.min(15, rows.length);
  for (let i = 0; i < maxScan; i++) {
    const rowVals = (rows[i] || []).filter(v => v !== null && v !== undefined && String(v).trim() !== "");
    let score = 0;
    for (const [canonical, aliases] of Object.entries(COLUMN_ALIASES)) {
      if (rowVals.some(cell => matchColumn(String(cell), aliases))) score++;
    }
    if (score > bestScore) { bestScore = score; headerIdx = i; }
  }
  if (bestScore < 2) return { error: "헤더 행을 찾을 수 없습니다." };

  // 열 매핑
  const colMap = {};
  const headerRow = rows[headerIdx] || [];
  headerRow.forEach((value, idx) => {
    if (value === null || value === undefined) return;
    const header = String(value).trim();
    for (const [canonical, aliases] of Object.entries(COLUMN_ALIASES)) {
      if (!(canonical in colMap) && matchColumn(header, aliases)) { colMap[canonical] = idx; break; }
    }
  });
  if (!("품명" in colMap)) {
    for (let idx = 0; idx < headerRow.length; idx++) {
      const v = headerRow[idx];
      if (v !== null && v !== undefined && String(v).trim() !== "") { colMap["품명"] = idx; break; }
    }
  }

  const getCell = (row, canonical) => {
    const idx = colMap[canonical];
    if (idx === undefined) return null;
    const v = row[idx];
    return (v === null || v === undefined || String(v).trim() === "") ? null : v;
  };

  // 금액/단가 헤더의 단위 감지 (예: "금액(백만원)" → 1,000,000배, "단가(천원)" → 1,000배)
  // 협력사별 양식이 원 단위 대신 백만원/천원 단위로 표기하는 경우 대응
  const detectUnitMult = (headerText) => {
    const h = normalizeText(headerText);
    if (h.includes("백만원")) return 1000000;
    if (h.includes("천원")) return 1000;
    if (h.includes("억원")) return 100000000;
    return 1;
  };
  const amountMult = ("금액" in colMap) ? detectUnitMult(String(headerRow[colMap["금액"]] || "")) : 1;
  const priceMult = ("단가" in colMap) ? detectUnitMult(String(headerRow[colMap["단가"]] || "")) : amountMult;

  // No(번호) 열 탐색 - 계층형 견적서(부분별 소계) 처리용
  let noColIdx = -1;
  headerRow.forEach((value, idx) => {
    if (value === null || value === undefined) return;
    const norm = normalizeText(String(value).trim());
    if (noColIdx === -1 && (norm === "no" || norm === "no." || norm === "번호" || norm === "itemno")) noColIdx = idx;
  });
  const getNo = (row) => {
    if (noColIdx === -1) return "";
    const v = row[noColIdx];
    return (v === null || v === undefined) ? "" : String(v).trim();
  };
  // No 값에서 이름 추출: "(1)기구설계" → "기구설계", "1) MAIN_FRAME" → "MAIN_FRAME"
  const nameFromNo = (noVal) => {
    if (!noVal) return "";
    let m = noVal.match(/^\(\d+\)\s*(.*)$/);
    if (m) return m[1].trim();
    m = noVal.match(/^\d+\)\s*(.*)$/);
    if (m) return m[1].trim();
    return "";
  };
  // 부분별 소계(Unit 소계) 행 판별:
  //  - No에 "Unit명" 포함 → Unit 소계
  //  - "(n)" 헤더 행이고 다음 유효 행이 "n)" 상세 행 → Unit 소계
  const isUnitSubtotal = new Array(rows.length).fill(false);
  if (noColIdx !== -1) {
    for (let r = headerIdx + 1; r < rows.length; r++) {
      const noVal = getNo(rows[r] || []);
      if (!noVal) continue;
      if (normalizeText(noVal).includes("unit명")) { isUnitSubtotal[r] = true; continue; }
      if (/^\(\d+\)/.test(noVal)) {
        for (let r2 = r + 1; r2 < rows.length; r2++) {
          const nextRow = rows[r2] || [];
          if (!nextRow.some(v => v !== null && v !== undefined && String(v).trim() !== "")) continue;
          if (/^\d+\)/.test(getNo(nextRow))) isUnitSubtotal[r] = true;
          break;
        }
      }
    }
  }

  const items = [];
  let originalTotal = 0, taxAmount = 0, totalRowText = "";

  // 섹션 컨텍스트 사전 계산 (규칙 2):
  //  - 구분 셀이 있는 행 → 그 아래 항목들에 컨텍스트 전달 (기존)
  //  - "가공품 소계" 같은 하단 소계 행 → 그 소계가 묶은 위쪽 항목들(이전 소계/섹션 이후)에도 컨텍스트 부여
  const sectionHintMap = new Array(rows.length).fill("");
  {
    // 1) 구분/No 셀에 섹션 마커가 있는 행 기록 + 하단 소계 행(구매품/가공품) 수집
    // (실제 파일에서 "가공품 소계"는 No 열에 표기되는 경우가 있음)
    const ownHint = {};
    const subtotalRows = []; // {row, hint}
    const markerOf = (row) => {
      const c = getCell(row, "구분");
      if (c) return String(c).replace(/\s+/g, "");
      // No 셀: 섹션 마커 형태(소계, [n] 섹션, Unit명)만 인정 — 일반 항목 번호("1)") 제외
      const n = getNo(row);
      if (n) {
        const h = String(n).replace(/\s+/g, "");
        if (h.includes("소계") || /^\[\d+\]/.test(h) || h.includes("unit명")) return h;
      }
      return "";
    };
    for (let r = headerIdx + 1; r < rows.length; r++) {
      const row = rows[r] || [];
      const values = row.filter(v => v !== null && v !== undefined && String(v).trim() !== "");
      if (values.length === 0) continue;
      const h = markerOf(row);
      if (h) {
        ownHint[r] = h;
        // "소계"가 포함된 행만 하단 소계로 취급 ("구매품 소개" 같은 상단 헤더 제외)
        if (h.includes("소계") && Object.values(SECTION_CLASSIFICATION).some(kws => kws.some(kw => h.includes(kw)))) {
          subtotalRows.push({ row: r, hint: h });
        }
      }
    }
    // 2) 하단 소계 행: 소계가 묶은 위쪽 항목 행(마커 없는 행)에 컨텍스트 부여
    // 경계 = 소계 직전 중 섹션 마커가 있는 마지막 행
    for (const st of subtotalRows) {
      let start = headerIdx;
      for (let r = st.row - 1; r > headerIdx; r--) {
        if (ownHint[r]) { start = r; break; }
      }
      for (let r = start + 1; r < st.row; r++) {
        if (!ownHint[r] && !sectionHintMap[r]) sectionHintMap[r] = st.hint;
      }
    }
    // 3) 나머지 행: 마지막 알려진 컨텍스트를 아래로 전파
    let cur = "";
    for (let r = headerIdx + 1; r < rows.length; r++) {
      if (ownHint[r]) cur = ownHint[r];
      else if (sectionHintMap[r]) cur = sectionHintMap[r];
      sectionHintMap[r] = cur;
    }
  }

  for (let r = headerIdx + 1; r < rows.length; r++) {
    const row = rows[r] || [];
    const values = row.filter(v => v !== null && v !== undefined && String(v).trim() !== "");
    if (values.length === 0) continue;

    const noVal = getNo(row);
    const name = getCell(row, "품명");
    const spec = getCell(row, "사양");
    const qtyRaw = getCell(row, "수량");
    const priceRaw = getCell(row, "단가");
    const amountRaw = getCell(row, "금액");
    const remark = getCell(row, "비고");
    const catHintCell = getCell(row, "구분");
    const vendor = getCell(row, "업체명");

    // 섹션 컨텍스트: 구분 셀이 있으면 그것, 없으면 사전 계산된 섹션 컨텍스트
    // (셀에 줄바꿈이 섞여 있을 수 있음 → 공백 전부 제거)
    const catHint = catHintCell ? String(catHintCell).replace(/\s+/g, "") : sectionHintMap[r];

    // 합산 수식 행 스킵 (예: 금액 셀이 =I18+I27 — 소계 합산 표기 행은 견적 항목이 아님)
    // 같은 행의 =단가*수량 수식은 실제 항목이므로 유지
    if (sumRows && sumRows.has(r)) continue;

    const rowText = values.map(String).join(" ");
    const isTotal = isTotalRow(rowText);
    const isTax = isTotal && ["부가세", "vat", "세금", "tax"].some(kw => normalizeText(rowText).includes(normalizeText(kw)));

    let amount = parseAmount(amountRaw) * amountMult;
    // 수량 셀이 비어 있을 때만 1로 간주. 명시적 0(예: "해외 셋업 제외" 행)은 0으로 유지
    const quantity = (qtyRaw === null || qtyRaw === undefined || String(qtyRaw).trim() === "") ? 1 : parseAmount(qtyRaw);
    const unitPrice = priceRaw ? parseAmount(priceRaw) * priceMult : 0;
    // 금액 셀이 비어 있을 때만 수량×단가로 보정 (엑셀의 금액 셀은 항상 신뢰)
    if (amountRaw === null && quantity > 0 && unitPrice) amount = quantity * unitPrice;

    if (isTax) { taxAmount += Math.abs(amount); continue; }
    if (isTotal) {
      // "합계" 행만(소계 제외) 최종 합계 후보로 갱신
      if (amount > 0 && normalizeText(rowText).includes("합계")) { originalTotal = amount; totalRowText = rowText; }
      continue;
    }
    // Unit 소계 행(예: "(1) Unit명 : BASE_FRAME"): 금액이 아래 상세에 이미 포함되어 있어 스킵
    if (isUnitSubtotal[r]) continue;
    // 품명도 No도 없는 행(장비 대수, 하단 메모 등 메타데이터 행)
    if (!name && !noVal) continue;

    // 품명이 비어 있으면 No 열에서 이름 추출: "(1)기구설계" → "기구설계"
    let itemName = name ? String(name).trim() : "";
    if (itemName === "-" || itemName === "--") itemName = "";
    if (!itemName) itemName = nameFromNo(noVal);
    if (!itemName && amount === 0) continue;

    items.push({
      id: "item_" + Math.random().toString(36).slice(2, 10),
      source_file: filename, source_sheet: sheetName, source_row: r + 1,
      name: itemName, spec: spec ? String(spec).trim() : "",
      quantity, unit_price: unitPrice, amount,
      remark: remark ? String(remark).trim() : "",
      category_hint: catHint,
      vendor: vendor ? String(vendor).trim() : "",
      scenario,
      auto_category: "미분류", confidence: 0, keywords: [], reason: "",
      final_category: "미분류", is_modified: false, is_tax: false, is_total_row: false,
    });
  }

  // 요약형 양식 폴백: 상세 항목이 0개인데 총합계 행이 있으면 합계 자체를 단일 항목으로 채택
  // (부분명+금액만 있는 요약 견적서도 분석 가능하게)
  if (items.length === 0 && originalTotal > 0) {
    const label = totalRowText.replace(/\s+/g, " ").replace(/\s*[\d,]+$/, "").trim() || "총합계";
    items.push({
      id: "item_" + Math.random().toString(36).slice(2, 10),
      source_file: filename, source_sheet: sheetName, source_row: 0,
      name: label, spec: "", quantity: 1, unit_price: 0, amount: originalTotal,
      remark: "요약형 양식 - 상세 내역 없음, 총합계 기준",
      category_hint: "", vendor: "", scenario,
      auto_category: "미분류", confidence: 0, keywords: [], reason: "",
      final_category: "미분류", is_modified: false, is_tax: false, is_total_row: false,
    });
  }

  return {
    items, originalTotal, taxAmount,
    extractedTotal: items.reduce((s, i) => s + i.amount, 0),
  };
}

// ─── PDF 파싱 (pdf.js) ───────────────────────────────────────
async function parsePDF(arrayBuffer, filename, scenario) {
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const items = [];
  let originalTotal = 0, taxAmount = 0;
  let totalText = "";

  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const content = await page.getTextContent();
    // 행 재구성 (y 좌표 기준)
    const lines = {};
    content.items.forEach(it => {
      const y = Math.round(it.transform[5]);
      if (!lines[y]) lines[y] = [];
      lines[y].push({ x: it.transform[4], str: it.str });
    });
    const sortedY = Object.keys(lines).map(Number).sort((a, b) => b - a);
    const pageLines = sortedY.map(y =>
      lines[y].sort((a, b) => a.x - b.x).map(o => o.str).join(" ").trim()
    ).filter(Boolean);

    totalText += pageLines.join("\n");

    pageLines.forEach((line, idx) => {
      if (isTotalRow(line)) {
        const isTaxLine = ["부가세", "vat", "세금", "tax"].some(kw => line.toLowerCase().includes(kw));
        const nums = line.match(/\d[\d,]*(\.\d+)?/g) || [];
        if (isTaxLine) {
          // 부가세/세금 행: 세금만 기록, 합계는 덮어쓰지 않음
          if (nums.length) taxAmount = parseAmount(nums[nums.length - 1]);
        } else if (nums.length) {
          const val = parseAmount(nums[nums.length - 1]);
          if (val > 0) originalTotal = val;
        }
        return;
      }
      if (line.length < 3 || !/\d/.test(line)) return;

      // 토큰 분리 (공백 기준). 모델번호(SUS304, T=3 등)는 숫자로 오인하지 않도록
      // "깨끗한 숫자"(숫자로 시작, 숫자/쉼표/소수점만)만 숫자로 취급.
      const tokens = line.split(/\s+/).map(s => s.trim()).filter(Boolean);
      const isCleanNum = t => /^\d[\d,]*(\.\d+)?$/.test(t);
      const numbers = [], textParts = [];
      tokens.forEach(t => {
        if (isCleanNum(t)) numbers.push(parseAmount(t));
        else textParts.push(t);
      });
      if (!numbers.length) return;

      let amount = numbers[numbers.length - 1];
      let quantity = 1, unitPrice = 0;
      if (numbers.length >= 3) { quantity = numbers[numbers.length - 3]; unitPrice = numbers[numbers.length - 2]; }
      else if (numbers.length === 2) {
        if (numbers[0] <= 100) { quantity = numbers[0]; unitPrice = numbers[1]; }
        else { unitPrice = numbers[0]; amount = numbers[1]; }
      }
      const name = textParts.slice(0, 2).join(" ");
      const spec = textParts.slice(2).join(" ");
      if (!name && amount === 0) return;

      items.push({
        id: "item_" + Math.random().toString(36).slice(2, 10),
        source_file: filename, source_sheet: `Page ${p}`, source_row: idx + 1,
        name, spec, quantity, unit_price: unitPrice, amount,
        remark: "", category_hint: "", vendor: "", scenario,
        auto_category: "미분류", confidence: 0, keywords: [], reason: "",
        final_category: "미분류", is_modified: false, is_tax: false, is_total_row: false,
      });
    });
  }

  const isScanned = totalText.trim().length < 50;
  return { items, originalTotal, taxAmount, isScanned,
           extractedTotal: items.reduce((s, i) => s + i.amount, 0) };
}

// ─── 사용자 규칙 저장 (localStorage) ─────────────────────────
const RULES_KEY = "quotation_rules";
function loadRules() {
  try { return JSON.parse(localStorage.getItem(RULES_KEY)) || {}; } catch { return {}; }
}
function saveRules(rules) {
  localStorage.setItem(RULES_KEY, JSON.stringify(rules));
}
function learnFromCorrection(name, spec, category) {
  const rules = loadRules();
  const text = normalizeText(`${name} ${spec}`);
  if (!text) return null;
  for (const kw of Object.keys(rules)) {
    if (text.includes(normalizeText(kw))) return null;
  }
  const keyword = (name || "").trim() || text.slice(0, 20);
  if (!keyword) return null;
  rules[keyword] = category;
  saveRules(rules);
  return keyword;
}

// ─── 내보내기 (CSV) ──────────────────────────────────────────
function toCSV(rows) {
  return rows.map(r => r.map(c => {
    const s = String(c === null || c === undefined ? "" : c);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(",")).join("\n");
}
function downloadCSV(filename, rows) {
  const blob = new Blob(["\uFEFF" + toCSV(rows)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ─── Excel 내보내기 (SheetJS) ────────────────────────────────
// sheets: { 시트이름: 2D 배열 }
function exportExcel(filename, sheets) {
  const wb = XLSX.utils.book_new();
  Object.entries(sheets).forEach(([name, rows]) => {
    const ws = XLSX.utils.aoa_to_sheet(rows);
    // 열 너비 자동 조정
    const colCount = Math.max(1, ...rows.map(r => r.length));
    ws["!cols"] = Array.from({ length: colCount }, (_, c) => {
      const wch = Math.max(...rows.map(r => String(r[c] === null || r[c] === undefined ? "" : r[c]).length), 8);
      return { wch: Math.min(40, wch + 2) };
    });
    XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31));
  });
  XLSX.writeFile(wb, filename);
}

// 전역 노출
window.QA = {
  COST_CATEGORIES, COST_GROUPS, GROUP_NAMES, GROUP_COLORS, DEFAULT_STACK_ORDER, CATEGORY_COLORS,
  DEFAULT_SCENARIOS, SUPPLY_OPTIONS, AMOUNT_UNITS,
  normalizeText, parseAmount, formatAmount, autoDetectUnit, safeDivide,
  classifyItem, propagateSimilar, aggregateScenario, groupTotals, computeDeltas,
  parseExcelSheet, parsePDF,
  loadRules, saveRules, learnFromCorrection,
  toCSV, downloadCSV, exportExcel,
};
