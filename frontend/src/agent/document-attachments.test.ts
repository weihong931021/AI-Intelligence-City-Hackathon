import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";

import { documentAttachmentAdapter, extractDocumentText, MAX_DOCUMENT_BYTES } from "./document-attachments";

describe("document imports", () => {
  it("reads UTF-8 CSV without losing Chinese, quoted prices or empty columns", async () => {
    const text = await extractDocumentText(new File(['\uFEFF標的,地號,單價,備註\n比較標的1,樹林區樹德段284地號,"130,167",\n'], "案件.csv"));
    expect(text).toContain('A2="比較標的1"');
    expect(text).toContain('B2="樹林區樹德段284地號"');
    expect(text).toContain('C2="130,167"');
    expect(text).toContain('D1="備註"');
  });

  it.each(["xlsx", "xls"] as const)("reads every nonempty sheet in %s, including displayed dates", async (bookType) => {
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([["估價基準日", "地號"], ["111年9月1日", "樹林區樹德段1415地號"]]), "比準地");
    XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet([["比較標的1", 130167]]), "實例");
    const file = new File([XLSX.write(book, { type: "array", bookType })], `案件.${bookType}`);
    const text = await extractDocumentText(file);
    expect(text).toContain("工作表：比準地");
    expect(text).toContain("111年9月1日");
    expect(text).toContain("工作表：實例");
    expect(text).toContain("130167");
  });

  it("rejects unsupported, empty and oversized documents with visible reasons", async () => {
    await expect(extractDocumentText(new File(["text"], "image.png"))).rejects.toThrow("支援");
    await expect(extractDocumentText(new File([""], "empty.csv"))).rejects.toThrow("空白");
    await expect(extractDocumentText(new File([new Uint8Array(MAX_DOCUMENT_BYTES + 1)], "large.pdf"))).rejects.toThrow("10 MB");
  });

  it("keeps failures on the attachment and includes extracted content only when sent", async () => {
    const states = [];
    for await (const state of documentAttachmentAdapter.add({ file: new File(["地號\n樹林區樹德段1415地號"], "案件.csv") })) states.push(state);
    expect(states[0].status.type).toBe("running");
    expect(states.at(-1)?.status.type).toBe("requires-action");
    const sent = await documentAttachmentAdapter.send(states.at(-1)!);
    expect(sent.status.type).toBe("complete");
    expect(sent.content).toEqual(expect.arrayContaining([expect.objectContaining({ type: "text", text: expect.stringContaining("樹林區樹德段1415地號") }), expect.objectContaining({ type: "data", name: "landlens-document" })]));
    const errors = [];
    for await (const state of documentAttachmentAdapter.add({ file: new File([], "empty.csv") })) errors.push(state);
    expect(errors.at(-1)?.status).toMatchObject({ type: "incomplete", message: expect.stringContaining("空白") });
  });
});
