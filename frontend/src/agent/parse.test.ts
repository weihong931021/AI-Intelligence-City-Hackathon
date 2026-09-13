import { describe, expect, it } from "vitest";
import { parseCaseText } from "./parse";
import { emptyCase, findMissing, mergeCase } from "./schema";

const SAMPLE = `比準地：地號 新北市樹林區樹德段1415地號、估價基準日 111年9月1日、區段 P001-00
標的1：地號 新北市樹林區樹德段284地號、單價 130,167、交易日期 110年9月14日、區段 P002-00
標的2：地號 新北市樹林區太平段367地號、單價 135,275、交易日期 111年1月11日、區段 P003-00
標的3：地號 新北市樹林區文林段317地號、單價 170,909、交易日期 110年10月29日、區段 P004-00`;

describe("parseCaseText", () => {
  it("parses the full sample into subject + 3 comparables", () => {
    const c = parseCaseText(SAMPLE);
    expect(c.subject).toEqual({
      parcel: "新北市樹林區樹德段1415地號",
      baseDate: "111年9月1日",
      zone: "P001-00",
    });
    expect(c.comparables[0]).toEqual({
      caseNo: "1",
      parcel: "新北市樹林區樹德段284地號",
      unitPrice: "130167",
      tradeDate: "110年9月14日",
      zone: "P002-00",
    });
    expect(c.comparables[2].zone).toBe("P004-00");
    expect(c.comparables[2].unitPrice).toBe("170909");
    expect(findMissing(c)).toEqual([]);
  });

  it("accepts 比較標的 / fullwidth punctuation / explicit 實例編號", () => {
    const c = parseCaseText(
      "比較標的２：實例編號 2；地號 新北市樹林區太平段917地號；單價 135275；交易日期 1110111；區段 Ｐ００３－００",
    );
    expect(c.comparables[1]).toEqual({
      caseNo: "2",
      parcel: "新北市樹林區太平段917地號",
      unitPrice: "135275",
      tradeDate: "1110111",
      zone: "P003-00",
    });
  });

  it("reports missing fields when input is partial", () => {
    const c = parseCaseText("比準地 新北市樹林區樹德段1415地號 P001-00\n標的1 單價 130,167");
    const missing = findMissing(c);
    const keys = missing.map((m) => `${m.target}.${m.key}`);
    expect(keys).toContain("subject.baseDate");
    expect(keys).toContain("comparable-1.parcel");
    expect(keys).toContain("comparable-1.tradeDate");
    expect(keys).toContain("comparable-1.zone");
    expect(keys).not.toContain("comparable-1.unitPrice");
    expect(keys).not.toContain("subject.parcel");
    // 標的2、3 完全沒給 → 各缺 5 項
    expect(missing.filter((m) => m.target === "comparable-2")).toHaveLength(5);
  });

  it("returns an empty case for unrelated text", () => {
    expect(parseCaseText("你好")).toEqual(emptyCase());
    expect(findMissing(parseCaseText("你好"))).toHaveLength(18);
  });
});

describe("mergeCase", () => {
  it("later values override, empty values do not", () => {
    const a = parseCaseText("比準地 新北市樹林區樹德段1415地號 P001-00");
    const b = parseCaseText("比準地 估價基準日 111年9月1日");
    const m = mergeCase(a, b);
    expect(m.subject).toEqual({
      parcel: "新北市樹林區樹德段1415地號",
      zone: "P001-00",
      baseDate: "111年9月1日",
    });
  });
});
