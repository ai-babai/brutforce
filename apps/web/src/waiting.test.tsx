import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { shuffleWineNotes, wineNotes } from "./wineNotes";

const receipt = { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-25T09:00:00Z", bytes: 5, mime: "image/jpeg", width: 100, height: 100 };
let finishSearch: (value: unknown) => void;
const currentFact = () => document.querySelector("#UI-004 .air-wine-note p")?.textContent;
const tick = async (ms: number) => { await act(async () => { vi.advanceTimersByTime(ms); }); };
const upload = async () => {
  fireEvent.change(screen.getByLabelText(/Загрузить фотографию этикетки/), {
    target: { files: [new File(["image"], "wine.jpg", { type: "image/jpeg" })] },
  });
  await act(async () => { await Promise.resolve(); });
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0);
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:waiting-photo"), revokeObjectURL: vi.fn() });
  vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos"
    ? Promise.resolve({ ok: true, status: 200, json: async () => receipt })
    : new Promise((resolve) => { finishSearch = (data) => resolve({ ok: true, status: 200, json: async () => data }); })));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("waiting screen", () => {
  it("preserves the deck through slow search and restarts the reading interval after pause", async () => {
    render(<App />);
    await upload();
    const first = currentFact();
    const deck = shuffleWineNotes(() => 0);
    expect(first).toBe(wineNotes[deck[0]]);
    await tick(1200);
    expect(screen.getByText("Нужно ещё немного времени")).toBeVisible();
    expect(currentFact()).toBe(first);
    await tick(3800);
    fireEvent.click(screen.getByRole("button", { name: "Приостановить заметки" }));
    await tick(20000);
    expect(currentFact()).toBe(first);
    expect(document.querySelector("#UI-004 .scan-line")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Продолжить заметки" }));
    await tick(7999);
    expect(currentFact()).toBe(first);
    await tick(1);
    expect(currentFact()).toBe(wineNotes[deck[1]]);
  });

  it("suspends notes for photo preview and hidden tab, then stops on result", async () => {
    render(<App />);
    await upload();
    const first = currentFact();
    await tick(2000);
    fireEvent.click(screen.getByRole("button", { name: "Открыть исходную фотографию" }));
    await tick(20000);
    expect(currentFact()).toBe(first);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть фотографию" }));
    await tick(1000);
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    fireEvent(document, new Event("visibilitychange"));
    await tick(20000);
    expect(currentFact()).toBe(first);
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => { finishSearch({ demo: false, candidates: [] }); });
    expect(screen.getByText("Ничего не найдено")).toBeVisible();
    await tick(8000);
    expect(document.querySelector("#UI-004")).toBeNull();
  });

  it("keeps the fact static under reduced motion while search completes", async () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    render(<App />);
    await upload();
    const first = currentFact();
    await tick(20000);
    expect(currentFact()).toBe(first);
    await act(async () => { finishSearch({ demo: false, candidates: [] }); });
    expect(screen.getByText("Ничего не найдено")).toBeVisible();
  });

  it("wires full shuffled cycles and a new search without an immediate repeat", async () => {
    render(<App />);
    await upload();
    const seen = [currentFact()];
    for (let index = 1; index < wineNotes.length; index += 1) {
      await tick(8000);
      seen.push(currentFact());
    }
    expect(new Set(seen).size).toBe(wineNotes.length);
    expect(new Set(seen)).toEqual(new Set(wineNotes));
    await tick(8000);
    const firstNextCycle = currentFact();
    expect(firstNextCycle).not.toBe(seen.at(-1));
    fireEvent.click(screen.getByRole("button", { name: "Отменить поиск" }));
    await upload();
    expect(currentFact()).not.toBe(firstNextCycle);
  });
});
