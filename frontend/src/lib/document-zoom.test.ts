import { describe, expect, it } from "vitest";

import { getWheelZoom, pagePointAt, scrollForPagePoint, ZOOM_MAX, ZOOM_MIN } from "./document-zoom";

describe("document zoom anchoring", () => {
  it("keeps the point under the cursor when a centered page grows wider than the viewport", () => {
    const cursor = { x: 640, y: 360 };
    const point = pagePointAt(cursor, { left: 240, top: 80, width: 800, height: 1000 });
    const scroll = scrollForPagePoint(
      { x: 0, y: 120 }, point, { left: 124, top: 80, width: 1200, height: 1500 }, cursor,
    );
    expect(scroll).toEqual({ x: 84, y: 260 });
    expect(124 + point.x * 1200 - scroll.x).toBeCloseTo(cursor.x);
    expect(80 + point.y * 1500 - (scroll.y - 120)).toBeCloseTo(cursor.y);
  });

  it("anchors to the actual page, including fixed padding and gaps above later pages", () => {
    const cursor = { x: 450, y: 200 };
    const point = pagePointAt(cursor, { left: 50, top: -100, width: 800, height: 1000 });
    expect(scrollForPagePoint(
      { x: 100, y: 1500 }, point, { left: 50, top: 400, width: 1200, height: 1500 }, cursor,
    )).toEqual({ x: 300, y: 2150 });
  });

  it("allows a pinch midpoint to move without changing the document point held by the fingers", () => {
    expect(scrollForPagePoint(
      { x: 200, y: 300 }, { x: 0.5, y: 0.5 },
      { left: -200, top: -300, width: 1000, height: 1000 }, { x: 350, y: 240 },
    )).toEqual({ x: 150, y: 260 });
  });
});

describe("trackpad pinch zoom", () => {
  it("zooms smoothly in both directions and reverses the same gesture", () => {
    const enlarged = getWheelZoom(1, -20, 0, 800);
    expect(enlarged).toBeGreaterThan(1);
    expect(getWheelZoom(enlarged, 20, 0, 800)).toBeCloseTo(1);
  });

  it("normalizes wheel delta units", () => {
    expect(getWheelZoom(1, -1, 1, 800)).toBe(getWheelZoom(1, -16, 0, 800));
    expect(getWheelZoom(1, -0.02, 2, 800)).toBe(getWheelZoom(1, -16, 0, 800));
  });

  it("honors the supported range and can zoom back from either limit", () => {
    expect(getWheelZoom(2, -1000, 0, 800)).toBe(ZOOM_MAX);
    expect(getWheelZoom(1, 1000, 0, 800)).toBe(ZOOM_MIN);
    expect(getWheelZoom(ZOOM_MAX, 1, 0, 800)).toBeLessThan(ZOOM_MAX);
    expect(getWheelZoom(ZOOM_MIN, -1, 0, 800)).toBeGreaterThan(ZOOM_MIN);
  });

  it("ignores invalid wheel deltas", () => {
    expect(getWheelZoom(1.5, Number.NaN, 0, 800)).toBe(1.5);
    expect(getWheelZoom(1.5, Number.POSITIVE_INFINITY, 0, 800)).toBe(1.5);
  });
});
