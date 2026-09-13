/**
 * 表4 比較法調查估價表 — 使用者必須提供的輸入。
 *
 * 比準地 3 項、比較標的各 5 項（依範本藍字格推定）。
 */

export type SubjectInput = {
  /** 地號，例：新北市樹林區樹德段1415地號 */
  parcel?: string;
  /** 估價基準日（比準地的「交易日期」列），例：111年9月1日 */
  baseDate?: string;
  /** 地價區段號，例：P001-00 */
  zone?: string;
};

export type ComparableInput = {
  /** 實例編號 1 / 2 / 3 */
  caseNo?: string;
  /** 地號 */
  parcel?: string;
  /** 土地正常單價（元/㎡） */
  unitPrice?: string;
  /** 交易日期 */
  tradeDate?: string;
  /** 地價區段號 */
  zone?: string;
};

export type CaseInput = {
  subject: SubjectInput;
  comparables: [ComparableInput, ComparableInput, ComparableInput];
};

export const SUBJECT_FIELDS: { key: keyof SubjectInput; label: string; hint: string }[] = [
  { key: "parcel", label: "地號", hint: "例：新北市樹林區樹德段1415地號" },
  { key: "baseDate", label: "估價基準日", hint: "例：111年9月1日" },
  { key: "zone", label: "地價區段號", hint: "例：P001-00" },
];

export const COMPARABLE_FIELDS: { key: keyof ComparableInput; label: string; hint: string }[] = [
  { key: "caseNo", label: "實例編號", hint: "例：1" },
  { key: "parcel", label: "地號", hint: "例：新北市樹林區樹德段284地號" },
  { key: "unitPrice", label: "土地正常單價", hint: "例：130,167" },
  { key: "tradeDate", label: "交易日期", hint: "例：110年9月14日" },
  { key: "zone", label: "地價區段號", hint: "例：P002-00" },
];

export type MissingField = {
  /** "subject" 或 "comparable-1" ... "comparable-3" */
  target: "subject" | `comparable-${1 | 2 | 3}`;
  targetLabel: string;
  key: string;
  label: string;
  hint: string;
};

export function emptyCase(): CaseInput {
  return { subject: {}, comparables: [{}, {}, {}] };
}

export function findMissing(input: CaseInput): MissingField[] {
  const missing: MissingField[] = [];
  for (const f of SUBJECT_FIELDS) {
    if (!input.subject[f.key]) {
      missing.push({ target: "subject", targetLabel: "比準地", key: f.key, label: f.label, hint: f.hint });
    }
  }
  input.comparables.forEach((c, i) => {
    const n = (i + 1) as 1 | 2 | 3;
    for (const f of COMPARABLE_FIELDS) {
      if (!c[f.key]) {
        missing.push({
          target: `comparable-${n}`,
          targetLabel: `比較標的${n}`,
          key: f.key,
          label: f.label,
          hint: f.hint,
        });
      }
    }
  });
  return missing;
}

export function isComplete(input: CaseInput): boolean {
  return findMissing(input).length === 0;
}

/** 後填的值覆蓋先填的值；空值不覆蓋。 */
export function mergeCase(base: CaseInput, patch: CaseInput): CaseInput {
  const merged = emptyCase();
  merged.subject = { ...base.subject };
  for (const f of SUBJECT_FIELDS) {
    if (patch.subject[f.key]) merged.subject[f.key] = patch.subject[f.key];
  }
  for (let i = 0; i < 3; i++) {
    merged.comparables[i] = { ...base.comparables[i] };
    for (const f of COMPARABLE_FIELDS) {
      if (patch.comparables[i][f.key]) merged.comparables[i][f.key] = patch.comparables[i][f.key];
    }
  }
  return merged;
}
