import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

type CatalogPage = {
  demo: boolean;
  candidates: typeof cabernet[];
  catalogVersion: string;
  nextCursor?: string;
};

const cabernet = {
  id: "cabernet",
  name: "Каберне",
  winery: "Долина",
  image: "/catalog/cabernet.webp",
  description: "Собранное описание.",
};
const merlot = { ...cabernet, id: "merlot", name: "Мерло" };
const page = (candidates: typeof cabernet[], nextCursor?: string): CatalogPage => ({
  demo: false,
  candidates,
  catalogVersion: "test-v2",
  ...(nextCursor ? { nextCursor } : {}),
});
const response = (data: CatalogPage) => ({ ok: true, json: async () => data });

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: Error) => void };
const deferred = <T,>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => { resolve = nextResolve; reject = nextReject; });
  return { promise, resolve, reject };
};

const openSearch = () => {
  fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
  const input = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
  input.focus();
  return input;
};
const catalogCalls = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/v2/catalog"));
const advance = async (milliseconds: number) => {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("FE-052 live catalog search", () => {
  it("CAT015 coalesces rapid typing into one request for the latest query", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(response(page([cabernet]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();

    fireEvent.change(input, { target: { value: "К" } });
    fireEvent.change(input, { target: { value: "Ка" } });
    fireEvent.change(input, { target: { value: "Каб" } });
    expect(document.activeElement).toBe(input);
    await advance(249);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    await advance(1);
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    expect(catalogCalls(fetchMock)[0][0]).toContain("q=%D0%9A%D0%B0%D0%B1");
  });

  it("CAT015 debounces the first nonblank character for 250ms and keeps loading, results, empty state, and focus inline", async () => {
    vi.useFakeTimers();
    const first = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn(() => first.promise);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();

    fireEvent.change(input, { target: { value: "К" } });
    expect(screen.getByLabelText(/Название вина/i)).toBe(input);
    await advance(249);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    await advance(1);
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    expect(screen.getByTestId("UI-008")).toBeVisible();
    expect(screen.getByRole("status", { name: "Ищем вина…" })).toBeVisible();
    expect(document.activeElement).toBe(input);

    await act(async () => { first.resolve(response(page([cabernet]))); await Promise.resolve(); });
    expect(screen.getByText("Каберне")).toBeVisible();
    expect(screen.getByTestId("UI-008")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Каберне" })).not.toBeInTheDocument();
  });

  it("CAT015 renders empty and failed requests inline, and retries the same query without navigation", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(page([])))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(response(page([cabernet])));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();

    fireEvent.change(input, { target: { value: "Нет" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Не нашли вина по этому запросу")).toBeVisible();
    expect(screen.getByTestId("UI-008")).toBeVisible();

    fireEvent.change(input, { target: { value: "Ошибка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByRole("alert", { name: "Не удалось загрузить вина" })).toBeVisible();
    expect(screen.getByTestId("UI-008")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await act(async () => { await Promise.resolve(); });
    expect(catalogCalls(fetchMock).at(-1)![0]).toContain("q=%D0%9E%D1%88%D0%B8%D0%B1%D0%BA%D0%B0");
    expect(screen.getByText("Каберне")).toBeVisible();
  });

  it("CAT016 invalidates an in-flight request immediately during the next debounce window and ignores late success and error", async () => {
    vi.useFakeTimers();
    const stale = deferred<ReturnType<typeof response>>();
    const staleError = deferred<ReturnType<typeof response>>();
    const fresh = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((_: string, init: RequestInit) =>
      [stale.promise, staleError.promise, fresh.promise][catalogCalls(fetchMock).length - 1],
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();

    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    const staleSignal = catalogCalls(fetchMock)[0][1].signal as AbortSignal;
    fireEvent.change(input, { target: { value: "Каб" } });
    expect(staleSignal.aborted).toBe(true);
    await act(async () => { stale.resolve(response(page([merlot]))); await Promise.resolve(); });
    expect(screen.queryByText("Мерло")).not.toBeInTheDocument();
    await advance(250);
    const staleErrorSignal = catalogCalls(fetchMock)[1][1].signal as AbortSignal;
    fireEvent.change(input, { target: { value: "Кабе" } });
    expect(staleErrorSignal.aborted).toBe(true);
    await act(async () => { staleError.reject(new TypeError("late error")); await Promise.resolve(); });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await advance(250);
    await act(async () => { fresh.resolve(response(page([cabernet]))); await Promise.resolve(); });
    expect(screen.getByText("Каберне")).toBeVisible();
  });

  it("CAT017 clears to the first catalog page and cancels deferred and in-flight work when leaving search", async () => {
    vi.useFakeTimers();
    const active = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn(() => active.promise);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    const querySignal = catalogCalls(fetchMock)[0][1].signal as AbortSignal;
    fireEvent.click(screen.getByRole("button", { name: "Очистить поиск" }));
    expect(querySignal.aborted).toBe(true);
    expect(document.activeElement).toBe(input);
    expect(catalogCalls(fetchMock)[1][0]).toBe("/v2/catalog?limit=24&cursor=&q=");

    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    expect((catalogCalls(fetchMock)[1][1].signal as AbortSignal).aborted).toBe(true);
    await act(async () => { active.resolve(response(page([cabernet]))); await Promise.resolve(); });
    expect(screen.getByTestId("UI-001")).toBeVisible();
    expect(screen.queryByText("Каберне")).not.toBeInTheDocument();
  });

  it("CAT017 cancels a queued debounce when leaving search before it fires", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(response(page([cabernet]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "К" } });
    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    expect(screen.getByTestId("UI-001")).toBeVisible();
  });

  it("CAT018 defers IME composition, while form submit and the search button cancel the timer and send only one immediate request", async () => {
    vi.useFakeTimers();
    const pending = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn(() => pending.promise);
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();

    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "Каб" } });
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    fireEvent.submit(input.closest("form")!);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    fireEvent.compositionEnd(input, { data: "Каб" });
    await advance(249);
    expect(catalogCalls(fetchMock)).toHaveLength(0);
    fireEvent.submit(input.closest("form")!);
    await act(async () => { await Promise.resolve(); });
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    fireEvent.submit(input.closest("form")!);
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(1);

    await act(async () => { pending.resolve(response(page([cabernet]))); await Promise.resolve(); });
    fireEvent.change(input, { target: { value: "Каберне" } });
    fireEvent.click(screen.getByRole("button", { name: "Искать" }));
    await act(async () => { await Promise.resolve(); });
    expect(catalogCalls(fetchMock)).toHaveLength(2);
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(2);
  });

  it("CAT019 resets cursor and replaces the current page when the query changes", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((url: string) => Promise.resolve(
      response(url.includes("cursor=next") ? page([merlot]) : page([cabernet], "next")),
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Мерло")).toBeVisible();
    fireEvent.change(input, { target: { value: "Каб" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    const calls = catalogCalls(fetchMock);
    expect(calls.at(-1)![0]).toBe("/v2/catalog?limit=24&cursor=&q=%D0%9A%D0%B0%D0%B1");
    expect(screen.queryByText("Мерло")).not.toBeInTheDocument();
  });

  it("CAT019 keeps loaded rows visible after an append error and retries that same cursor", async () => {
    vi.useFakeTimers();
    let appendAttempts = 0;
    const fetchMock = vi.fn((url: string) => {
      if (!url.includes("cursor=next")) return Promise.resolve(response(page([cabernet], "next")));
      appendAttempts += 1;
      return appendAttempts === 1
        ? Promise.reject(new TypeError("offline"))
        : Promise.resolve(response(page([merlot])));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Каберне")).toBeVisible();
    expect(screen.getByRole("alert", { name: /Не удалось загрузить вина/i })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Мерло")).toBeVisible();
    expect(catalogCalls(fetchMock).at(-1)![0]).toContain("cursor=next");
  });

  it("CAT019 aborts an obsolete append and ignores its late page after a query change", async () => {
    vi.useFakeTimers();
    const staleAppend = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((url: string) =>
      url.includes("cursor=next")
        ? staleAppend.promise
        : Promise.resolve(response(page([cabernet], "next"))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    const staleSignal = catalogCalls(fetchMock).at(-1)![1].signal as AbortSignal;
    fireEvent.change(input, { target: { value: "Каб" } });
    expect(staleSignal.aborted).toBe(true);
    await act(async () => { staleAppend.resolve(response(page([merlot]))); await Promise.resolve(); });
    expect(screen.queryByText("Мерло")).not.toBeInTheDocument();
    await advance(250);
    expect(catalogCalls(fetchMock).at(-1)![0]).toBe("/v2/catalog?limit=24&cursor=&q=%D0%9A%D0%B0%D0%B1");
  });

  it("CAT020 preserves the query, order, scroll, and cursor after choosing an appended card and using Back", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((url: string) => Promise.resolve(response(
      url.includes("cursor=after") ? page([{ ...cabernet, id: "third", name: "Третье вино" }]) : url.includes("cursor=next") ? page([merlot], "after") : page([cabernet], "next"),
    )));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await act(async () => { await Promise.resolve(); });
    const list = screen.getByText("Мерло").closest("button")!;
    const content = screen.getByTestId("UI-008").parentElement!;
    Object.defineProperty(content, "scrollTop", { configurable: true, value: 180, writable: true });
    fireEvent.click(list);
    expect(screen.getByRole("heading", { name: "Мерло" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    expect(screen.getByTestId("UI-008")).toBeVisible();
    expect(screen.getByLabelText(/Название вина/i)).toHaveValue("Ка");
    expect(screen.getByText("Каберне")).toBeVisible();
    expect(screen.getByText("Мерло")).toBeVisible();
    expect(content.scrollTop).toBe(180);
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    await act(async () => { await Promise.resolve(); });
    expect(catalogCalls(fetchMock).at(-1)![0]).toContain("cursor=after");
  });

  it("CAT017 clears composition state on leave so a normal query after re-entry can run", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(response(page([cabernet]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "К" } });
    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    fireEvent.click(screen.getByRole("button", { name: "Поиск" }));
    const reentered = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
    reentered.focus();
    fireEvent.change(reentered, { target: { value: "Ка" } });
    await advance(250);
    expect(catalogCalls(fetchMock)).toHaveLength(1);
  });

  it("CAT017 clears active composition and permits the next fresh composition", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(response(page([cabernet]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "К" } });
    fireEvent.click(screen.getByRole("button", { name: "Очистить поиск" }));
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    expect(catalogCalls(fetchMock)[0][0]).toBe("/v2/catalog?limit=24&cursor=&q=");
    expect(input).toHaveValue("");
    // The cancelled composition may never emit compositionend. A fresh one must work.
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "Мер" } });
    fireEvent.compositionEnd(input, { data: "Мер" });
    await advance(250);
    expect(catalogCalls(fetchMock)).toHaveLength(2);
    expect(catalogCalls(fetchMock)[1][0]).toContain("q=%D0%9C%D0%B5%D1%80");
    fireEvent.compositionEnd(input, { data: "Мер" });
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(2);
  });

  it("CAT017 restores a correction result and cancels both queued and active catalog work on Back", async () => {
    vi.useFakeTimers();
    const correction = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((url: string) =>
      catalogCalls(fetchMock).length === 1
        ? Promise.resolve(response(page([cabernet])))
        : correction.promise,
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const input = openSearch();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByText("Каберне").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Не это вино? Исправить" }));
    const correctionInput = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
    correctionInput.focus();
    fireEvent.change(correctionInput, { target: { value: "М" } });
    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    await advance(300);
    expect(catalogCalls(fetchMock)).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Каберне" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Не это вино? Исправить" }));
    const activeInput = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
    activeInput.focus();
    fireEvent.change(activeInput, { target: { value: "Ме" } });
    await advance(250);
    const signal = catalogCalls(fetchMock)[1][1].signal as AbortSignal;
    fireEvent.click(screen.getByRole("button", { name: /Назад/i }));
    expect(signal.aborted).toBe(true);
    await act(async () => { correction.resolve(response(page([merlot]))); await Promise.resolve(); });
    expect(screen.getByRole("heading", { name: "Каберне" })).toBeVisible();
  });

  it("CAT020 runs the same live search from the home and bottom-navigation entries", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => Promise.resolve(response(page([cabernet]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /По названию/i }));
    let input = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
    input.focus();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Каберне")).toBeVisible();

    cleanup();
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Поиск" }));
    input = screen.getByLabelText(/Название вина/i) as HTMLInputElement;
    input.focus();
    fireEvent.change(input, { target: { value: "Ка" } });
    await advance(250);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Каберне")).toBeVisible();
    expect(catalogCalls(fetchMock)).toHaveLength(2);
  });
});
