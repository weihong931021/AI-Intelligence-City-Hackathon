import { type CaseInput, type ComparableInput, type SubjectInput, emptyCase } from "./schema";

/** 全形數字、標點轉半形，方便統一比對。 */
function normalize(text: string): string {
  return text
    .replace(/[０-９]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xff10 + 0x30))
    .replace(/[Ａ-Ｚ]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xff21 + 0x41))
    .replace(/[，、]/g, ",")
    .replace(/：/g, ":")
    .replace(/；/g, ";")
    .replace(/－/g, "-")
    .replace(/[ \t]+/g, " ");
}

const DATE_RE = /(\d{2,3}年\s*\d{1,2}月\s*\d{1,2}日|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|(?<![\d,])\d{7}(?![\d,]))/;
const ZONE_RE = /\b([A-Z]\d{3}-\d{2})\b/;
const PARCEL_RE = /((?:新北市|臺北市|台北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|[一-鿿]{2,3}[縣市])?[一-鿿]{1,4}[區鄉鎮市][一-鿿]{1,6}段(?:[一-鿿]{1,4}小段)?\s*[\d-]+(?:地號)?)/;
const PRICE_LABEL_RE = /(?:正常單價|單價|價格)\s*[:：]?\s*([\d,]{4,})/;
const PRICE_BARE_RE = /(?<![\d,年月日/-])(\d{1,3}(?:,\d{3})+|\d{5,7})(?![\d,]|年|月|日|地號|段)/;
const CASENO_RE = /(?:實例編號|編號)\s*[:：]?\s*(\d+)/;

/** 抓出「比準地 / 比較標的N」段落。回傳 [標籤, 內文]。 */
function splitSegments(text: string): { role: "subject" | "comparable"; index: number; body: string }[] {
  // 段落標頭：比準地、標的1、比較標的1、比較標的的1、標的一
  const headRe = /(比準地|比較標的的?\s*([1-3一二三])|標的\s*([1-3一二三]))\s*[:：]?/g;
  const heads: { start: number; end: number; role: "subject" | "comparable"; index: number }[] = [];
  const cn: Record<string, number> = { 一: 1, 二: 2, 三: 3 };
  let m: RegExpExecArray | null;
  while ((m = headRe.exec(text)) !== null) {
    const numRaw = m[2] ?? m[3];
    if (m[1] === "比準地") {
      heads.push({ start: m.index, end: m.index + m[0].length, role: "subject", index: 0 });
    } else if (numRaw) {
      const n = cn[numRaw] ?? Number(numRaw);
      heads.push({ start: m.index, end: m.index + m[0].length, role: "comparable", index: n - 1 });
    }
  }
  return heads.map((h, i) => ({
    role: h.role,
    index: h.index,
    body: text.slice(h.end, heads[i + 1]?.start ?? text.length),
  }));
}

function parseSubject(body: string): SubjectInput {
  const s: SubjectInput = {};
  const parcel = PARCEL_RE.exec(body)?.[1];
  if (parcel) s.parcel = parcel.replace(/\s+/g, "");
  const bodyNoParcel = parcel ? body.replace(parcel, " ") : body;
  const date = DATE_RE.exec(bodyNoParcel)?.[1];
  if (date) s.baseDate = date.replace(/\s+/g, "");
  const zone = ZONE_RE.exec(bodyNoParcel)?.[1];
  if (zone) s.zone = zone;
  return s;
}

function parseComparable(body: string, index: number): ComparableInput {
  const c: ComparableInput = {};
  const parcel = PARCEL_RE.exec(body)?.[1];
  if (parcel) c.parcel = parcel.replace(/\s+/g, "");
  let rest = parcel ? body.replace(parcel, " ") : body;

  const caseNo = CASENO_RE.exec(rest)?.[1];
  if (caseNo) {
    c.caseNo = caseNo;
    rest = rest.replace(CASENO_RE, " ");
  } else {
    // 標頭本身就寫了「標的N」，實例編號視同已提供。
    c.caseNo = String(index + 1);
  }

  const date = DATE_RE.exec(rest)?.[1];
  if (date) {
    c.tradeDate = date.replace(/\s+/g, "");
    rest = rest.replace(date, " ");
  }

  const zone = ZONE_RE.exec(rest)?.[1];
  if (zone) {
    c.zone = zone;
    rest = rest.replace(zone, " ");
  }

  const price = PRICE_LABEL_RE.exec(rest)?.[1] ?? PRICE_BARE_RE.exec(rest)?.[1];
  if (price) c.unitPrice = price.replace(/,/g, "");
  return c;
}

/**
 * 從一段自由文字抓出表4 需要的輸入。抓不到的欄位維持 undefined。
 */
export function parseCaseText(raw: string): CaseInput {
  const text = normalize(raw);
  const out = emptyCase();
  for (const seg of splitSegments(text)) {
    if (seg.role === "subject") {
      Object.assign(out.subject, parseSubject(seg.body));
    } else if (seg.index >= 0 && seg.index < 3) {
      Object.assign(out.comparables[seg.index], parseComparable(seg.body, seg.index));
    }
  }
  return out;
}
