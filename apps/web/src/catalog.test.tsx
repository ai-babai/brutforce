import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getCatalog } from "./api";
import { App } from "./App";

const wine = {
  id: "real-cabernet",
  name: "Каберне",
  winery: "Долина",
  image: "/catalog-assets/v42/images/cabernet-640.webp",
  description: "Собранное описание.",
  sourceUrl: "https://catalog.example/wines/cabernet",
  sourceSnapshotDate: "2026-09-20",
  imageVariants: [
    { role: "thumbnail", path: "/catalog-assets/v42/images/cabernet-160.webp", width: 160, height: 240, bytes: 1000, mimeType: "image/webp", sha256: "a" },
    { role: "card", path: "/catalog-assets/v42/images/cabernet-640.webp", width: 640, height: 960, bytes: 3000, mimeType: "image/webp", sha256: "b" },
    { role: "original", path: "/catalog-assets/v42/images/cabernet-original.webp", width: 640, height: 960, bytes: 3500, mimeType: "image/webp", sha256: "c" },
  ],
};
const page = (candidates: unknown[], nextCursor?: string, demo = false) => ({ demo, candidates, catalogVersion: "v42", ...(nextCursor ? { nextCursor } : {}) });
const response = (data: unknown, ok = true) => ({ ok, json: async () => data });

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("BE-045 catalog display", () => {
  it("CAT003 exposes variant attributes, de-duplicates widths, and falls back on image errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(page([wine]))));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
    const thumbnail = await screen.findByAltText("Фото вина: Каберне");
    expect(thumbnail).toHaveAttribute("src", wine.imageVariants[0].path);
    expect(thumbnail).toHaveAttribute("srcset", expect.stringContaining("640w"));
    expect(thumbnail).toHaveAttribute("loading", "eager");
    expect(thumbnail.getAttribute("srcset")!.match(/640w/g)).toHaveLength(1);
    fireEvent.error(thumbnail);
    expect(await screen.findByLabelText("Фото Каберне недоступно")).toBeVisible();
  });

  it("CAT003 lazy-loads rows below the first four visible images", async () => {
    const wines = Array.from({ length: 5 }, (_, index) => ({ ...wine, id: `wine-${index}`, name: `Вино ${index}` }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(page(wines))));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
    expect((await screen.findByAltText("Фото вина: Вино 0"))).toHaveAttribute("loading", "eager");
    expect(screen.getByAltText("Фото вина: Вино 4")).toHaveAttribute("loading", "lazy");
  });

  it("CAT004 keeps tasting color prose out of compact search rows", async () => {
    const candidate = { ...wine, color: "Лимонный цвет с зеленоватым оттенком", sugar: "сухое" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(page([candidate]))));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
    const row = await screen.findByRole("button", { name: /Каберне/i });
    expect(row).toHaveTextContent("сухое");
    expect(row).not.toHaveTextContent("Лимонный цвет");
  });

  it.each([
    {
      name: "unknown facts and invalid numeric values",
      candidate: { ...wine, id: "unknown", year: undefined, alcoholPercent: Number.NaN, alcoholMinPercent: 15, alcoholMaxPercent: 10, volumeL: Number.NaN },
      visible: ["Год не указан"], absent: ["Алкоголь", "Объём", "Категория", "Цвет", "Сахар"],
    },
    {
      name: "a valid alcohol range without inventing an exact value",
      candidate: { ...wine, id: "range", alcoholMinPercent: 11, alcoholMaxPercent: 13 },
      visible: ["11–13%"], absent: [],
    },
    {
      name: "Abrau retains sugar without category or color",
      candidate: { ...wine, id: "abrau", name: "Abrau", sugar: "брют", categoryAndColor: "Категория и цвет" },
      visible: ["брют"], absent: ["Категория", "Цвет", "Категория и цвет"],
    },
    {
      name: "СКБ retains sugar without category or color",
      candidate: { ...wine, id: "skb", name: "СКБ", sugar: "полусухое", categoryAndColor: "Категория и цвет" },
      visible: ["полусухое"], absent: ["Категория", "Цвет", "Категория и цвет"],
    },
    {
      name: "ESSE retains color without category or sweetness",
      candidate: { ...wine, id: "esse", name: "ESSE", color: "красное", categoryAndColor: "Категория и цвет" },
      visible: ["красное"], absent: ["Категория", "Сахар", "Категория и цвет"],
    },
  ])("CAT004 CAT005 shows $name", async ({ candidate, visible, absent }) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(page([candidate]))));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
    await user.click(await screen.findByRole("button", { name: new RegExp(candidate.name) }));
    for (const value of visible) expect((await screen.findAllByText(value))[0]).toBeVisible();
    for (const label of absent) expect(screen.queryByText(label)).not.toBeInTheDocument();
  });

  it("CAT007 shows real provenance and does not label a real catalog card as demo", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url.startsWith("/v2/catalog") ? response(page([wine])) : response({ demo: false, candidates: [] }),
    )));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
    await user.click(await screen.findByRole("button", { name: /Каберне/i }));
    expect(screen.queryByText("Демо-карточка")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть на сайте «Своё Вино»/ })).toHaveAttribute("href", wine.sourceUrl);
  });

  it("CAT007 keeps a photo recognition reference notice alongside real provenance", async () => {
    const receipt = { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-20T12:00:00Z", bytes: 5, mime: "image/jpeg", width: 100, height: 100 };
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:photo") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(response(
      url === "/v1/photos" ? receipt
        : url === "/v1/search" ? { demo: true, candidates: [wine], selectedId: wine.id }
        : url === "/v1/recommendations" ? { demo: true, candidates: [] }
        : page([wine]),
    ))));
    render(<App />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText(/Загрузить фотографию/i), new File(["photo"], "wine.jpg", { type: "image/jpeg" }));
    await user.click(await screen.findByRole("button", { name: "Каберне" }));
    expect(screen.getByRole("heading", { name: "Каберне" })).toBeVisible();
    expect(screen.getByText("Reference")).toBeVisible();
    expect(screen.getByText("Reference-режим")).toBeVisible();
    expect(screen.queryByText(/Карточки и похожие варианты синтетические/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть на сайте «Своё Вино»/ })).toHaveAttribute("href", wine.sourceUrl);
  });

  it("CAT001 CAT002 searches the server and appends pages beyond the initial catalog page", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(
      url.includes("cursor=next") ? response(page([{ ...wine, id: "second", name: "Мерло" }])) : response(page([wine], "next")),
    ));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.type(screen.getByLabelText(/Название вина/i), "Каберне");
    await user.click(screen.getByRole("button", { name: "Искать" }));
    await screen.findByText("Каберне");
    expect(fetchMock.mock.calls[0][0]).toBe("/v2/catalog?limit=24&cursor=&q=%D0%9A%D0%B0%D0%B1%D0%B5%D1%80%D0%BD%D0%B5");
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByText("Мерло")).toBeVisible();
    expect(fetchMock.mock.calls[1][0]).toContain("cursor=next");
  });

  it("CAT002 aborts an obsolete catalog query and ignores its late result", async () => {
    let resolveFirst!: (value: ReturnType<typeof response>) => void;
    const fetchMock = vi.fn((url: string) => url.includes("q=%D0%9A%D0%B0")
      ? new Promise(resolve => { resolveFirst = resolve; })
      : Promise.resolve(response(page([{ ...wine, name: "Мерло" }]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    const input = screen.getByLabelText(/Название вина/i);
    await user.type(input, "Ка");
    await user.click(screen.getByRole("button", { name: "Искать" }));
    await user.click(screen.getByRole("button", { name: "Назад" }));
    await user.click(screen.getByRole("button", { name: "Поиск" }));
    const nextInput = screen.getByLabelText(/Название вина/i);
    await user.clear(nextInput);
    await user.type(nextInput, "Мерло");
    await user.click(screen.getByRole("button", { name: "Искать" }));
    resolveFirst(response(page([wine])));
    await waitFor(() => expect(screen.getByText("Мерло")).toBeVisible());
    expect(screen.queryByText("Каберне")).not.toBeInTheDocument();
    expect((((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].signal) as AbortSignal).aborted).toBe(true);
  });

  it("uses the paginated catalog contract", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(page([wine], "next")));
    vi.stubGlobal("fetch", fetchMock);
    await expect(getCatalog({ limit: 24, cursor: "next", q: "каберне" })).resolves.toMatchObject({ catalogVersion: "v42", nextCursor: "next" });
    expect(fetchMock).toHaveBeenCalledWith("/v2/catalog?limit=24&cursor=next&q=%D0%BA%D0%B0%D0%B1%D0%B5%D1%80%D0%BD%D0%B5", expect.any(Object));
  });
});
