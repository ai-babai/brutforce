import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const catalogCalls = () => vi.mocked(fetch).mock.calls.filter(([url]) => String(url).startsWith("/v2/catalog"));
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
const advance = async (milliseconds: number) => {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
};

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
      expect(screen.getByText("Этикетка вина")).toBeVisible();
      expect(screen.getByRole("button", { name: "Сделать снимок" })).toBeVisible();
      expect(screen.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
      expect(screen.getByLabelText("Изображение с камеры")).toBeVisible();
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
      expect(screen.getByRole("img", { name: "Загруженная фотография этикетки" })).toBeVisible();
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
    expect(screen.getByRole("button", { name: /Открыть исходную фотографию/i })).toBeVisible();
    expect(screen.getByText("Ваше фото")).toBeVisible();
    expect(document.querySelectorAll("#UI-010 .air-recovery-photo")).toHaveLength(1);
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
    const note = () => screen.getByLabelText("Заметка о вине").querySelector("p")?.textContent;
    const initial = note();
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(note()).not.toBe(initial);
    fireEvent.click(screen.getByRole("button", { name: /Приостановить заметки|Пауза/i }));
    const paused = note();
    await act(async () => { await vi.advanceTimersByTimeAsync(14000); });
    expect(note()).toBe(paused);
    expect(screen.getByRole("status")).toHaveTextContent(/Ищем|Поиск/i);
    expect(searchCalls()).toHaveLength(1);
    expect(screen.getByRole("button", { name: /Продолжить заметки|Возобновить/i })).toBeVisible();
    await act(async () => { finishSearch(response({ demo: true, candidates: [first] })); });
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
  });

  it("AIR-014 keeps notes static when reduced motion is active without stopping photo search", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, media: "(prefers-reduced-motion: reduce)", addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    const pending = deferred<ReturnType<typeof response>>();
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos" ? Promise.resolve(response(receipt)) : pending.promise));
    render(<App />);
    fireEvent.change(screen.getByLabelText(/Загрузить фотографию/i), { target: { files: [new File(["image"], "label.jpg", { type: "image/jpeg" })] } });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const note = screen.getByLabelText("Заметка о вине").querySelector("p") as HTMLParagraphElement;
    const text = note.textContent;
    await advance(21000);
    expect(note.textContent).toBe(text);
    expect(screen.getByRole("status")).toHaveTextContent(/Ищем|Поиск/i);
    expect(searchCalls()).toHaveLength(1);
    await act(async () => { pending.resolve(response({ demo: true, candidates: [first] })); });
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
  });

  it("AIR-002 keeps one accepted photo through waiting, candidates and card, then clears it on Home", async () => {
    const pending = deferred<ReturnType<typeof response>>();
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos" ? Promise.resolve(response(receipt)) : pending.promise));
    render(<App />);
    await upload();
    await waitFor(() => expect(searchCalls()).toHaveLength(1));
    expect(screen.getByRole("button", { name: /Открыть исходную фотографию/i })).toBeVisible();
    await act(async () => { pending.resolve(response({ demo: true, candidates: [first] })); });
    const row = await screen.findByRole("button", { name: /Резерв, 2023/i });
    expect(screen.getByRole("button", { name: /Открыть исходную фотографию/i })).toBeVisible();
    await userEvent.click(row);
    expect(screen.getByRole("button", { name: /Сверить с моим фото/i })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Главная" }));
    expect(screen.queryByRole("button", { name: /Открыть исходную фотографию|Продолжить поиск/i })).not.toBeInTheDocument();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-002 retains the accepted receipt for retry after a photo-search error", async () => {
    let searches = 0;
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos" ? receipt
      : ++searches === 1 ? { error: { code: "unavailable" } } : { demo: true, candidates: [first] },
    url === "/v1/photos" || searches !== 1, searches === 1 ? 503 : 200))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("heading", { name: /Не удалось получить ответ/i })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Повторить поиск/i }));
    expect(await screen.findByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(2);
    expect(JSON.parse((searchCalls()[1][1] as RequestInit).body as string).photoId).toBe(receipt.id);
  });

  it.each([
    { state: "results", reply: response({ demo: true, candidates: [first, second] }), heading: /Нашли похожие вина/i },
    { state: "empty", reply: response({ demo: true, candidates: [] }), heading: /Ничего не найдено/i },
    { state: "server", reply: response({ error: { code: "unavailable" } }, false, 503), heading: /Не удалось получить ответ/i },
    { state: "offline", reply: undefined, heading: /Похоже, нет сети/i },
  ])("AIR-004 offers independent camera and gallery from $state without replacing the photo early", async ({ reply, heading }) => {
    const mediaDevices = navigator.mediaDevices;
    const getUserMedia = vi.fn(() => new Promise<MediaStream>(() => {}));
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
    try {
      vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos" ? Promise.resolve(response(receipt))
        : reply ? Promise.resolve(reply) : Promise.reject(new TypeError("offline"))));
      render(<App />);
      await upload();
      expect(await screen.findByRole("heading", { name: heading })).toBeVisible();
      const picker = screen.getByLabelText(/Загрузить фотографию/i) as HTMLInputElement;
      const pickerClick = vi.spyOn(picker, "click");
      fireEvent.click(screen.getByRole("button", { name: /Галерея/i }));
      expect(pickerClick).toHaveBeenCalledOnce();
      expect(screen.getByRole("heading", { name: heading })).toBeVisible();
      fireEvent.click(screen.getByRole("button", { name: /Камера|Сделать новый снимок/i }));
      expect(screen.getByText("Этикетка вина")).toBeVisible();
      expect(getUserMedia).toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Назад" }));
      expect(screen.getByRole("heading", { name: heading })).toBeVisible();
      expect(photoCalls()).toHaveLength(1);
      expect(searchCalls()).toHaveLength(1);
    } finally {
      Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: mediaDevices });
    }
  });

  it.each(["screen", "system"])("AIR-009 restores the non-leading photo candidate through $back Back", async (back) => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first, second] }))));
    render(<App />);
    await upload();
    const other = await screen.findByRole("button", { name: /Резерв, 2021/i });
    const content = screen.getByTestId("app").querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 79;
    await userEvent.click(other);
    expect(screen.getByRole("heading", { name: second.name })).toBeVisible();
    expect(screen.getAllByText("2021").length).toBeGreaterThan(0);
    if (back === "screen") fireEvent.click(screen.getByRole("button", { name: "Назад" }));
    else fireEvent.popState(window);
    expect(screen.getAllByRole("button", { name: /Резерв, 20/i }).map((row) => row.getAttribute("aria-label")))
      .toEqual(["Резерв, 2023", "Резерв, 2021"]);
    expect(screen.getByRole("button", { name: /Открыть исходную фотографию/i })).toBeVisible();
    expect(content.scrollTop).toBe(79);
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-010 closes a photo preview onto the result that settled while it was open", async () => {
    const pending = deferred<ReturnType<typeof response>>();
    vi.stubGlobal("fetch", vi.fn((url) => url === "/v1/photos" ? Promise.resolve(response(receipt)) : pending.promise));
    render(<App />);
    await upload();
    await waitFor(() => expect(searchCalls()).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: /Открыть исходную фотографию/i }));
    expect(screen.getByRole("button", { name: /Закрыть фотографию/i })).toBeVisible();
    await act(async () => { pending.resolve(response({ demo: true, candidates: [first] })); });
    fireEvent.click(screen.getByRole("button", { name: /Закрыть фотографию/i }));
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    expect(screen.queryByRole("heading", { name: /Ищем/i })).not.toBeInTheDocument();
  });

  it("AIR-010 returns from a photo preview to its result list or chosen card", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first] }))));
    render(<App />);
    await upload();
    const row = await screen.findByRole("button", { name: /Резерв, 2023/i });
    const content = screen.getByTestId("app").querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 64;
    fireEvent.click(screen.getByRole("button", { name: /Открыть исходную фотографию/i }));
    fireEvent.click(screen.getByRole("button", { name: /Закрыть фотографию/i }));
    expect(row).toBeVisible();
    expect(content.scrollTop).toBe(64);
    fireEvent.click(row);
    fireEvent.click(screen.getByRole("button", { name: /Сверить с моим фото/i }));
    fireEvent.click(screen.getByRole("button", { name: /Закрыть фотографию/i }));
    expect(screen.getByRole("heading", { name: first.name })).toBeVisible();
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-013 retries upload of a retained file but never searches without a receipt", async () => {
    let attempts = 0;
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(url === "/v1/photos" && ++attempts === 1
      ? response({ error: { code: "upload_unavailable" } }, false, 503)
      : url === "/v1/photos" ? response(receipt) : response({ demo: true, candidates: [first] }))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("heading", { name: /Не удалось получить ответ/i })).toBeVisible();
    expect(searchCalls()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: /Повторить поиск/i }));
    expect(await screen.findByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    expect(photoCalls()).toHaveLength(2);
    expect(searchCalls()).toHaveLength(1);
    expect(JSON.parse((searchCalls()[0][1] as RequestInit).body as string).photoId).toBe(receipt.id);
  });

  it("AIR-005 replaces a settled result with a newly accepted gallery photo", async () => {
    const newer = { ...receipt, id: "fedcba9876543210fedcba9876543210" };
    let uploaded = 0;
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? ++uploaded === 1 ? receipt : newer
      : JSON.parse((searchCalls().at(-1)?.[1] as RequestInit).body as string).photoId === receipt.id
        ? { demo: true, candidates: [first] } : { demo: true, candidates: [second] }))));
    render(<App />);
    await upload();
    expect(await screen.findByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Галерея" }));
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию/i), new File(["new photo"], "new.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("button", { name: /Резерв, 2021/i })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Резерв, 2023/i })).not.toBeInTheDocument();
    expect(photoCalls()).toHaveLength(2);
    expect(searchCalls()).toHaveLength(2);
    expect(JSON.parse((searchCalls()[1][1] as RequestInit).body as string).photoId).toBe(newer.id);
  });

  it.each(["success", "error"])("AIR-005 ignores a late $outcome from photo A after starting B", async (outcome) => {
    const oldSearch = deferred<ReturnType<typeof response>>();
    const newer = { ...receipt, id: "fedcba9876543210fedcba9876543210" };
    let uploads = 0;
    vi.stubGlobal("fetch", vi.fn((url) => {
      if (url === "/v1/photos") return Promise.resolve(response(++uploads === 1 ? receipt : newer));
      return searchCalls().length === 1 ? oldSearch.promise : Promise.resolve(response({ demo: true, candidates: [second] }));
    }));
    render(<App />);
    await upload();
    await waitFor(() => expect(searchCalls()).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: /Отменить поиск/i }));
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию/i), new File(["new photo"], "new.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("button", { name: /Резерв, 2021/i })).toBeVisible();
    await act(async () => { oldSearch.resolve(outcome === "success"
      ? response({ demo: true, candidates: [first] })
      : response({ error: { code: "unavailable" } }, false, 503)); });
    expect(screen.getByRole("button", { name: /Резерв, 2021/i })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Резерв, 2023/i })).not.toBeInTheDocument();
    expect(searchCalls()).toHaveLength(2);
  });

  it("AIR-019 saves one wine, restores it after reload and removes only that wine", async () => {
    vi.stubGlobal("fetch", vi.fn((url) => Promise.resolve(response(url === "/v1/photos"
      ? receipt : { demo: true, candidates: [first] }))));
    const view = render(<App />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: /Резерв, 2023/i }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить вино" }));
    expect(screen.getByRole("button", { name: "Удалить из сохранённых" })).toHaveAttribute("aria-pressed", "true");
    view.unmount();
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getAllByRole("button", { name: /Резерв, 2023/i })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /Резерв, 2023/i }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить из сохранённых" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getByRole("heading", { name: "Пока ничего не сохранено" })).toBeVisible();
    expect(photoCalls()).toHaveLength(1);
    expect(searchCalls()).toHaveLength(1);
  });

  it("AIR-020 returns from a saved card to the same list and scroll without photo search", async () => {
    localStorage.setItem("wine-demo-saved-v1", JSON.stringify([first, second]));
    vi.stubGlobal("fetch", vi.fn());
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    const content = screen.getByTestId("app").querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 103;
    fireEvent.click(screen.getByRole("button", { name: /Резерв, 2021/i }));
    expect(screen.getByRole("heading", { name: second.name })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getAllByRole("button", { name: /Резерв, 20/i })).toHaveLength(2);
    expect(content.scrollTop).toBe(103);
    expect(searchCalls()).toHaveLength(0);
  });

  it("AIR-022 starts safely after lost photo-route history without invented photo or search", () => {
    window.history.replaceState({ brutforceCandidateResult: true }, "", "/?screen=results");
    vi.stubGlobal("fetch", vi.fn());
    render(<App />);
    fireEvent.popState(window);
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Сканировать вино/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Выбрать фото/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /По названию/i })).toBeVisible();
    expect(screen.queryByRole("img", { name: /Загруженная фотография/i })).not.toBeInTheDocument();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    window.history.replaceState({}, "", "/");
  });

  it("AIR-015 debounces visible input including IME, then submits explicitly without a duplicate", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ demo: true, catalogVersion: "v1", candidates: [first] }))));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
    const input = screen.getByLabelText(/Название вина/i);
    fireEvent.change(input, { target: { value: "К" } });
    await advance(249);
    expect(catalogCalls()).toHaveLength(0);
    await advance(1);
    expect(catalogCalls()).toHaveLength(1);
    expect(catalogCalls()[0][0]).toContain("q=%D0%9A");
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(100);
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    fireEvent.submit(input.closest("form")!);
    expect(catalogCalls()).toHaveLength(1);
    await advance(150);
    expect(catalogCalls()).toHaveLength(2);
    expect(catalogCalls()[1][0]).toContain("q=%D0%9A%D0%B0");
    fireEvent.compositionEnd(input, { data: "Ка" });
    await advance(250);
    expect(catalogCalls()).toHaveLength(2);
    fireEvent.change(input, { target: { value: "Каб" } });
    fireEvent.click(screen.getByRole("button", { name: "Искать" }));
    expect(catalogCalls()).toHaveLength(3);
    await advance(250);
    expect(catalogCalls()).toHaveLength(3);
    expect(input).toHaveValue("Каб");
  });

  it("AIR-016 ignores A, pages only B once and clears to one unfiltered first page", async () => {
    vi.useFakeTimers();
    const old = deferred<ReturnType<typeof response>>();
    const append = deferred<ReturnType<typeof response>>();
    const wines = Array.from({ length: 2038 }, (_, i) => ({ ...first, id: `wine-${i}`, name: `Вино ${i}` }));
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      if (url.endsWith("q=%D0%90")) return old.promise;
      if (url.includes("cursor=next")) return append.promise;
      return Promise.resolve(response({ demo: false, catalogVersion: "v1", candidates: wines.slice(0, 24), nextCursor: "next" }));
    }));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
    const input = screen.getByLabelText(/Название вина/i);
    fireEvent.change(input, { target: { value: "А" } });
    await advance(250);
    fireEvent.change(input, { target: { value: "Б" } });
    await advance(250);
    expect(screen.getByRole("button", { name: "Вино 23, 2023" })).toBeVisible();
    expect(document.querySelectorAll("#UI-008 .candidate-list > button")).toHaveLength(24);
    expect(catalogCalls()[1][0]).toBe("/v2/catalog?limit=24&cursor=&q=%D0%91");
    await act(async () => { old.resolve(response({ demo: false, catalogVersion: "v1", candidates: [second] })); });
    expect(screen.queryByRole("button", { name: /Резерв, 2021/i })).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: "Показать ещё" });
    fireEvent.click(more);
    expect(more).toBeDisabled();
    fireEvent.click(more);
    expect(catalogCalls().filter(([url]) => String(url).includes("cursor=next"))).toHaveLength(1);
    expect(catalogCalls().at(-1)?.[0]).toBe("/v2/catalog?limit=24&cursor=next&q=%D0%91");
    await act(async () => { append.resolve(response({ demo: false, catalogVersion: "v1", candidates: wines.slice(24, 48) })); });
    expect(screen.getByRole("button", { name: "Вино 47, 2023" })).toBeVisible();
    expect(document.querySelectorAll("#UI-008 .candidate-list > button")).toHaveLength(48);
    expect(catalogCalls().filter(([url]) => String(url).includes("cursor=next"))).toHaveLength(1);
    fireEvent.change(input, { target: { value: "" } });
    await act(async () => { await Promise.resolve(); });
    expect(document.querySelectorAll("#UI-008 .candidate-list > button")).toHaveLength(24);
    expect(catalogCalls().at(-1)?.[0]).toBe("/v2/catalog?limit=24&cursor=&q=");
  });

  it("AIR-016 keeps the current rows on 409 until a deliberate first-page refresh", async () => {
    vi.useFakeTimers();
    let firstPages = 0;
    vi.stubGlobal("fetch", vi.fn((url: string) => url.includes("cursor=next")
      ? Promise.resolve(response({}, false, 409))
      : Promise.resolve(response({ demo: false, catalogVersion: "v1", candidates: [++firstPages === 1 ? first : second],
        ...(firstPages === 1 ? { nextCursor: "next" } : {}) }))));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
    fireEvent.change(screen.getByLabelText(/Название вина/i), { target: { value: "Ка" } });
    await advance(250);
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    expect(screen.getByRole("button", { name: "Обновить результаты" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
    expect(catalogCalls()).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Обновить результаты" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("button", { name: /Резерв, 2021/i })).toBeVisible();
    expect(catalogCalls().at(-1)?.[0]).toBe("/v2/catalog?limit=24&cursor=&q=%D0%9A%D0%B0");
  });

  it("AIR-017 shows the cellar mascot only before manual search work begins", async () => {
    vi.useFakeTimers();
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(++calls === 3
      ? response({}, false, 503)
      : response({ demo: false, catalogVersion: "v1", candidates: calls === 1 ? [first] : [] }))));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
    const input = screen.getByLabelText(/Название вина/i);
    expect(document.querySelector("#UI-008 .mascot-scene-browse")).not.toBeNull();
    fireEvent.change(input, { target: { value: "А" } });
    expect(document.querySelector("#UI-008 .mascot-scene-browse")).toBeNull();
    await advance(250);
    expect(screen.getByRole("button", { name: /Резерв, 2023/i })).toBeVisible();
    fireEvent.change(input, { target: { value: "Б" } });
    await advance(250);
    expect(screen.getByText(/Не нашли вина по этому запросу/i)).toBeVisible();
    fireEvent.change(input, { target: { value: "В" } });
    await advance(250);
    expect(screen.getByRole("alert", { name: /Не удалось загрузить вина/i })).toBeVisible();
    expect(document.querySelector("#UI-008 .mascot-scene-browse")).toBeNull();
  });
});
