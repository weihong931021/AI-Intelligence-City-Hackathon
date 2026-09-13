import { type CaseInput, type MissingField, SUBJECT_FIELDS, COMPARABLE_FIELDS, emptyCase } from "./schema";

export type DocumentPayload = { name: string; text: string; images: { page: number; data: string }[] };
export type RecognizedField = { target: MissingField["target"]; key: string; value: string; source: string; evidence: string };
export type Recognition = { kind: "case" | "template" | "reference"; title: string; summary: string; fields: RecognizedField[]; warnings: string[] };
export type DocumentRecognition = Recognition & { attachmentId: string; filename: string };
export type DocumentRecognizer = (document: DocumentPayload, signal: AbortSignal) => Promise<Recognition>;

export const recognizeDocument: DocumentRecognizer = async (document, signal) => {
  const response = await fetch("/api/extract-case", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(document), signal,
  });
  if (!response.ok) throw new Error(`文件辨識服務回應 ${response.status}，請確認後端連線後按「重新產生」重試。`);
  const result = await response.json();
  if (!result || !["case", "template", "reference"].includes(result.kind) || typeof result.title !== "string" || typeof result.summary !== "string" || !Array.isArray(result.fields) || !Array.isArray(result.warnings)
    || result.fields.some((f: RecognizedField) => !f || !["subject", "comparable-1", "comparable-2", "comparable-3"].includes(f.target) || [f.key, f.value, f.source, f.evidence].some((v) => typeof v !== "string"))
    || result.warnings.some((w: unknown) => typeof w !== "string")) throw new Error("模型沒有回傳完整的辨識結果，請重新產生以重試。");
  return result;
};

/** 使用已擷取的原始值，不從模型的敘述或未對欄的文件全文猜欄位。 */
export function recognitionToCase(result: Pick<Recognition, "fields">): CaseInput {
  const input = emptyCase();
  for (const field of result.fields ?? []) {
    const isSubject = field.target === "subject";
    const fields = isSubject ? SUBJECT_FIELDS : COMPARABLE_FIELDS;
    if (!fields.some((f) => f.key === field.key) || typeof field.value !== "string" || !field.value.trim()) continue;
    const target = isSubject ? input.subject : input.comparables[Number(field.target.slice(-1)) - 1];
    if (!target) continue;
    Object.assign(target, { [field.key]: field.key === "unitPrice" ? field.value.replace(/[,，\s]/g, "") : field.value.trim() });
  }
  return input;
}
