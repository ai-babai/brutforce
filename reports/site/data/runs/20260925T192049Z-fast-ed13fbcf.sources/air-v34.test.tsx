import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const receipt = { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-19T09:00:00Z", bytes: 5, mime: "image/jpeg", width: 100, height: 100 };
const first = { id: "wine-a", name: "Резерв", winery: "Винодельня А", year: 2023, image: "", description: "Описание из каталога" };
const second = { ...first, id: "wine-b", year: 2021, winery: "Винодельня Б" };
const response = (data: unknown, ok = true, status = ok ? 200 : 503) => ({ ok, status, json: async () => data });
const upload = () => userEvent.upload(screen.getByLabelText(/Загрузить фотографию/i), new File(["image"], "label.jpg", { type: "image/jpeg" }));
const photoCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/photos");
const searchCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/search");

beforeEach(() => {
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:air-photo"), revokeObjectURL: vi.fn() });
});
afterEach(() => { cleanup(); localStorage.clear(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("Air 3.4 photo journey", () => {
  it("keeps the approved capture heading, actions and product navigation in the active Air skin", async () => {
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn(() => new Promise(() => {})) } });
    try {
      render(<App />);
      await userEvent.click(screen.getByRole("button", { name: /Сканировать вино/i }));
      expect(screen.getByRole("heading", { name: "Наведите на этикетку" })).toBeVisible();
      expect(screen.getByRole("button", { name: "Сделать снимок" })).toBeVisible();
      expect(screen.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
      const airCss = readFileSync(join(process.cwd(), "src/air.css"), "utf8");
      expect(airCss).toContain(".app .camera-page { height: 100%; max-height: none;");
      expect(airCss).toContain(".camera-page .viewfinder { height: clamp(180px, calc(100dvh - 540px), 390px)");
    } finally {
      Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: mediaDevices });
    }
  });

  it("AIR-001 ignores a receipt delivered after Home during upload", async () => {
    let finishUpload!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos"
      ? new Promise<ReturnType<typeof response>>((resolve) => { finishUpload = resolve; })
      : Promise.resolve(response({ demo: true, candidates: [first] }))));
    render(<App />);
    await upload();
    await waitFor(() => expect(photoCalls()).toHaveLength(1));
    await userEvent.click(screen.getByRole("button", { name: /Отменить поиск/i }));
    await act(async () => { finishUpload(response(receipt)); });
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Продолжить поиск/i })).not.toBeInTheDocument();
    expect(searchCalls()).toHaveLength(0);
  });

  it("AIR-001 clears Home and ignores a late photo-search success after cancellation", async () => {
    let finishSearch!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos"
      ? Promise.resolve(response(receipt))
      : new Promise<ReturnType<typeof response>>((resolve) => { finishSearch = resolve; })));
    render(<App />);
    await upload();
    await waitFor(() => expect(searchCalls()).toHaveLength(1));
    await userEvent.click(screen.getByRole("button", { name: /Отменить поиск/i }));
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(screen.queryAllByRole("button", { name: /Продолжить поиск|Удалить фото/i })).toHaveLength(0);
    await act(async () => { finishSearch(response({ demo: true, candidates: [first], selectedId: first.id })); });
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Резерв/i })).not.toBeInTheDocument();
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-007 keeps even a confident singleton in the list until selection", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first], selectedId: first.id }))));
    render(<App />);
    await upload();
    const row = await screen.findByRole("button", { name: /Резерв, 2023/i });
    expect(row).toBeVisible();
    expect(screen.getAllByRole("button", { name: /Резерв, 2023/i })).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: first.name })).not.toBeInTheDocument();
    await userEvent.click(row);
    expect(screen.getByRole("heading", { name: first.name })).toBeVisible();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-006 preserves ranked multi-candidate order and waits for a choice", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first, second], selectedId: second.id }))));
    render(<App />);
    await upload();
    const leader = await screen.findByRole("button", { name: /Резерв, 2023/i });
    const alternative = screen.getByRole("button", { name: /Резерв, 2021/i });
    expect(leader).toHaveClass("candidate-leader");
    expect([...document.querySelectorAll("#UI-006 .candidate-list > button")]).toEqual([leader, alternative]);
    expect(screen.queryByRole("heading", { name: first.name })).not.toBeInTheDocument();
    expect(searchCalls()).toHaveLength(1);
  });

  it("opens the saved shelf at its heading instead of inheriting photo-result scroll", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first] }))));
    render(<App />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: /Резерв, 2023/i }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить вино" }));
    const content = screen.getByTestId("app").querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 135;
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getByRole("heading", { name: "Сохранённое" })).toBeVisible();
    expect(content.scrollTop).toBe(0);
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
  });

  it("opens the catalog directly from an empty saved shelf", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ demo: true, catalogVersion: "fixture-v1", candidates: [first] }))));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getByRole("heading", { name: "Пока ничего не сохранено" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Открыть каталог" }));
    expect(await screen.findByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
  });

  it("AIR-003 gallery cancellation keeps the selected photo, ordered rows and scroll", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first, second], selectedId: second.id }))));
    render(<App />);
    await upload();
    await screen.findByRole("button", { name: /Резерв, 2023/i });
    const content = screen.getByTestId("app").querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 81;
    const picker = screen.getByLabelText(/Загрузить фотографию/i) as HTMLInputElement;
    const pickerClick = vi.spyOn(picker, "click");
    await userEvent.click(screen.getByRole("button", { name: /Галерея/i }));
    expect(pickerClick).toHaveBeenCalledOnce();
    fireEvent.change(picker, { target: { files: [] } });
    expect(screen.getByRole("img", { name: "Загруженная фотография этикетки" })).toHaveAttribute("src", "blob:air-photo");
    expect(screen.getAllByRole("button", { name: /Резерв, 20/i }).map((row) => row.getAttribute("aria-label")))
      .toEqual(["Резерв, 2023", "Резерв, 2021"]);
    expect(content.scrollTop).toBe(81);
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(1);
  });

  it.each([
    { state: "empty", heading: /Ничего не найдено/i },
    { state: "server", heading: /Не удалось получить ответ/i },
    { state: "network", heading: /Похоже, нет сети/i },
  ])("AIR-003 keeps the $state recovery state after gallery cancellation", async ({ state, heading }) => {
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos" ? Promise.resolve(response(receipt))
      : state === "network" ? Promise.reject(new TypeError("offline"))
        : Promise.resolve(state === "server" ? response({ error: { code: "unavailable" } }, false, 503)
          : response({ demo: true, candidates: [] }))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
    const picker = screen.getByLabelText(/Загрузить фотографию/i) as HTMLInputElement;
    const pickerClick = vi.spyOn(picker, "click");
    fireEvent.click(screen.getByRole("button", { name: /Галерея/i }));
    expect(pickerClick).toHaveBeenCalledOnce();
    fireEvent.change(picker, { target: { files: [] } });
    expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    if (state !== "empty") {
      expect(screen.queryByRole("img", { name: "Загруженная фотография этикетки" })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: state === "network" ? /Проверить ещё раз/i : /Повторить поиск/i }));
      await waitFor(() => expect(searchCalls()).toHaveLength(2));
      expect(JSON.parse((searchCalls()[1][1] as RequestInit).body as string).photoId).toBe(receipt.id);
    }
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(state === "empty" ? 1 : 2);
  });

  it.each([
    { failure: "service", reply: response({ error: { code: "unavailable" } }, false, 503) },
    { failure: "network", reply: undefined },
  ])("AIR-011 distinguishes $failure failure from an empty successful result", async ({ reply }) => {
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos"
      ? Promise.resolve(response(receipt))
      : reply ? Promise.resolve(reply) : Promise.reject(new TypeError("network unavailable"))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("heading", { name: reply ? /Не удалось получить ответ/i : /Похоже, нет сети/i })).toBeVisible();
    expect(screen.queryByRole("heading", { name: /Ничего не найдено|Вино не найдено/i })).not.toBeInTheDocument();
    expect(document.querySelector("#UI-010 .mascot-scene img")?.getAttribute("src")).toBe(reply
      ? "/assets/v2/server-error-a.png" : "/assets/v2/mascot-offline-2d-alpha.webp");
    expect(screen.queryByRole("button", { name: /Открыть исходную фотографию/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: reply ? /Повторить поиск/i : /Проверить ещё раз/i })).toBeVisible();
    expect(photoCalls()).toHaveLength(1);
  });

  it("AIR-012 retries failed search with the same accepted receipt and no second upload", async () => {
    let tries = 0;
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(url === "/v1/photos" ? response(receipt)
      : ++tries === 1 ? response({ error: { code: "unavailable" } }, false, 503)
      : response({ demo: true, candidates: [] }))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("heading", { name: /Не удалось получить ответ/i })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Повторить поиск/i }));
    expect(await screen.findByRole("heading", { name: /Ничего не найдено|Вино не найдено/i })).toBeVisible();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(2);
    expect((searchCalls()[1][1] as RequestInit).body).toBe((searchCalls()[0][1] as RequestInit).body);
    expect(JSON.parse((searchCalls()[1][1] as RequestInit).body as string).photoId).toBe(receipt.id);
    expect(screen.getByRole("button", { name: /Галерея/i })).toBeVisible();
  });

  it("AIR-008 shows only known structured facts in rows and keeps the full card", async () => {
    const known = { ...first, color: "красное", sugar: "сухое", alcoholPercent: 13.5 };
    const unknown = { ...first, id: "unknown", name: "Резерв без года", year: 0, winery: "", description: "Настоящее описание" };
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [known, unknown] }))));
    render(<App />);
    await upload();
    const knownRow = await screen.findByRole("button", { name: /Резерв, 2023/i });
    expect(knownRow).toHaveTextContent("2023");
    expect(knownRow).toHaveTextContent("Винодельня А");
    expect(knownRow).toHaveTextContent("красное сухое · 13.5%");
    const row = await screen.findByRole("button", { name: unknown.name });
    expect(row).toBeVisible();
    expect(row).not.toHaveTextContent(/Год не указан|Цена|Рейтинг|%/i);
    await userEvent.click(row);
    expect(screen.getByRole("heading", { name: unknown.name })).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Описание" }));
    expect(screen.getByText("Настоящее описание")).toBeVisible();
  });

  it("AIR-014 lets notes pause while search and readable status continue", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    let finishSearch!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos"
      ? Promise.resolve(response(receipt))
      : new Promise<ReturnType<typeof response>>((resolve) => { finishSearch = resolve; })));
    render(<App />);
    fireEvent.change(screen.getByLabelText(/Загрузить фотографию/i), { target: { files: [new File(["image"], "label.jpg", { type: "image/jpeg" })] } });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(searchCalls()).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent(/Ищем|Поиск/i);
    const note = screen.getByLabelText("Заметка о вине").querySelector("p") as HTMLParagraphElement;
    const initial = note.textContent;
    await act(async () => { await vi.advanceTimersByTimeAsync(7000); });
    expect(note.textContent).not.toBe(initial);
    fireEvent.click(screen.getByRole("button", { name: /Приостановить заметки|Пауза/i }));
    const paused = note.textContent;
    await act(async () => { await vi.advanceTimersByTimeAsync(14000); });
    expect(note.textContent).toBe(paused);
    expect(screen.getByRole("status")).toHaveTextContent(/Ищем|Поиск/i);
    expect(searchCalls()).toHaveLength(1);
    expect(screen.getByRole("button", { name: /Продолжить заметки|Возобновить/i })).toBeVisible();
    await act(async () => { finishSearch(response({ demo: true, candidates: [first] })); });
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
  });
});
