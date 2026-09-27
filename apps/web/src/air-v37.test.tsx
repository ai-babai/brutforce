import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const sourceUrl = "https://vino-svoe.ru/wines/portveyn-belyy-alushta";
const port = {
  id: "port", name: "Портвейн белый Алушта 2021", winery: "Массандра",
  image: "/catalog/port.webp", description: "Аромат сухофруктов и орехов.",
  sugar: "сладкое", alcoholPercent: 17, region: ["Крым"], sourceUrl,
};
const response = (data: unknown) => ({ ok: true, json: async () => data });
const page = (wines: unknown[]) => ({ demo: false, catalogVersion: "air37", candidates: wines });

afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function openCard(wine: object, extras: object[] = []) {
  const fetchMock = vi.fn((url: string) => Promise.resolve(response(
    url.startsWith("/v2/catalog") ? page([wine, ...extras]) : { demo: false, candidates: [] },
  )));
  vi.stubGlobal("fetch", fetchMock);
  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: /По названию/i }));
  await userEvent.click(screen.getByRole("button", { name: /Открыть каталог/i }));
  await userEvent.click(await screen.findByRole("button", { name: /Портвейн белый Алушта/i }));
  return fetchMock;
}

describe("FE-088 card behavior", () => {
  it("AIR-041 AIR-042 shows structured facts and no inferred year when year is absent", async () => {
    await openCard(port);
    const hero = document.querySelector("#UI-007 .result-hero")!;
    const facts = within(hero.querySelector(".result-facts") as HTMLElement);
    expect(facts.getByText("сладкое")).toBeVisible();
    expect(facts.getByText("17%")).toBeVisible();
    expect(facts.getByText("Крым")).toBeVisible();
    expect(hero.querySelectorAll(".result-fact svg")).toHaveLength(3);
    expect(hero.querySelector(".result-fact svg")?.textContent).not.toContain("%");
    expect(hero.querySelector(".result-winery")).toHaveTextContent(/^Массандра$/);
    expect(within(document.querySelector(".result-overview") as HTMLElement).getByText("Год не указан")).toBeVisible();
    expect(screen.getByRole("heading", { name: port.name })).toBeVisible();
  });

  it("AIR-041 consumes BE-089 variant widths and paths without alpha-specific filename rules", async () => {
    const media = { ...port, image: "/media/catalog/original/original.webp", imageVariants: [
      { role: "thumbnail", path: "/media/catalog/400/thumb.webp", width: 400, height: 700, bytes: 1, mimeType: "image/webp", sha256: "a" },
      { role: "card", path: "/media/catalog/800/card.webp", width: 800, height: 1400, bytes: 1, mimeType: "image/webp", sha256: "b" },
      { role: "original", path: "/media/catalog/original/original.webp", width: 1200, height: 2100, bytes: 1, mimeType: "image/webp", sha256: "c" },
    ] };
    await openCard(media);
    const image = document.querySelector(".result-shelf img")!;
    expect(image).toHaveAttribute("src", media.imageVariants[1].path);
    expect(image).toHaveAttribute("width", "800");
    expect(image).toHaveAttribute("height", "1400");
    expect(image).toHaveAttribute("srcset", expect.stringContaining("/media/catalog/400/thumb.webp 400w"));
    expect(image).toHaveAttribute("srcset", expect.stringContaining("/media/catalog/800/card.webp 800w"));
    expect(image).toHaveAttribute("srcset", expect.stringContaining("/media/catalog/original/original.webp 1200w"));
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: `Фото ${media.name} недоступно` })).toBeVisible();
  });

  it.each([2021, 0, undefined])("AIR-042 uses only positive structured year %s", async (year) => {
    await openCard({ ...port, year });
    expect(document.querySelector(".result-winery")).toHaveTextContent(year === 2021 ? "Массандра · 2021" : "Массандра");
    expect(document.querySelector(".result-winery")?.textContent).toBe(year === 2021 ? "Массандра · 2021" : "Массандра");
    expect(within(document.querySelector(".result-overview") as HTMLElement).getByText(year === 2021 ? "2021" : "Год не указан")).toBeVisible();
  });

  it("AIR-041 AIR-044 omits missing facts and an empty description, and has no tabs/correction", async () => {
    await openCard({ ...port, sugar: "", alcoholPercent: 0, region: [], description: "   ", sourceUrl: undefined });
    expect(document.querySelector(".result-facts")).toBeNull();
    expect(document.querySelector(".result-description")).toBeNull();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Не это вино\? Исправить/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Своё Вино/i })).not.toBeInTheDocument();
  });

  it("AIR-043 AIR-044 keeps a direct secure source separate from closed description", async () => {
    const fetchMock = await openCard(port);
    const link = screen.getByRole("link", { name: /Открыть на сайте «Своё Вино»/i });
    expect(link).toHaveTextContent("Открыть на сайте «Своё Вино» ↗");
    expect(link).toHaveAttribute("href", sourceUrl);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    const details = document.querySelector(".result-description") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.previousElementSibling).toHaveClass("result-overview");
    await userEvent.click(within(details).getByText("О вкусе и сочетаниях"));
    expect(details.open).toBe(true);
    expect(within(details).getByText(port.description)).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => url === "/v1/feedback")).toBe(false);
  });

  it("AIR-043 rejects unsafe stored source URLs", async () => {
    localStorage.setItem("wine-demo-saved-v1", JSON.stringify([{ ...port, sourceUrl: "javascript:alert(1)" }]));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [] })));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(screen.getByRole("button", { name: /Портвейн белый Алушта/i }));
    expect(screen.queryByRole("link", { name: /Своё Вино/i })).not.toBeInTheDocument();
  });

  it("AIR-043 keeps photo-feedback distinct from a real source link", async () => {
    const receipt = { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-27T00:00:00Z", bytes: 5, mime: "image/jpeg", width: 2, height: 2 };
    const fetchMock = vi.fn((url: string) => Promise.resolve(response(url === "/v1/photos" ? receipt
      : url === "/v1/search" ? { demo: false, candidates: [port], feedbackToken: "11111111111111111111111111111111" }
        : { demo: false, candidates: [] })));
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:photo") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), new File(["photo"], "wine.jpg", { type: "image/jpeg" }));
    await userEvent.click(await screen.findByRole("button", { name: /Портвейн белый Алушта/i }));
    expect(screen.getByRole("link", { name: /Открыть на сайте «Своё Вино»/i })).toHaveAttribute("href", sourceUrl);
    expect(screen.getByRole("heading", { name: "Разметить мою фотографию" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Нет, это другое вино" })).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => url === "/v1/feedback")).toBe(false);
  });

  it("AIR-045 Back restores the candidate list for choosing another wine", async () => {
    await openCard({ ...port, year: 2021 }, [{ ...port, id: "second", name: "Другое вино", year: 2022 }]);
    await userEvent.click(screen.getByRole("button", { name: "Сохранить вино" }));
    expect(screen.getByRole("button", { name: "Удалить из сохранённых" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByRole("button", { name: /Другое вино/i })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Другое вино/i }));
    expect(screen.getByRole("heading", { name: "Другое вино" })).toBeVisible();
    fireEvent.popState(window);
    expect(screen.getByRole("button", { name: /Портвейн белый Алушта/i })).toBeVisible();
  });
});
