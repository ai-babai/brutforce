import { describe, expect, it } from "vitest";
import { shuffleWineNotes, wineNotes } from "./wineNotes";

describe("waiting notes deck", () => {
  it("shows each of the twelve facts once per cycle and avoids a boundary repeat", () => {
    const first = shuffleWineNotes(() => 0);
    const second = shuffleWineNotes(() => 0, first.at(-1));
    expect(wineNotes).toHaveLength(12);
    expect(new Set(first).size).toBe(12);
    expect(new Set(second).size).toBe(12);
    expect(second[0]).not.toBe(first.at(-1));
  });

  it("uses the supplied random sequence to change the order", () => {
    expect(shuffleWineNotes(() => 0)).not.toEqual(shuffleWineNotes(() => 0.999));
  });
});
