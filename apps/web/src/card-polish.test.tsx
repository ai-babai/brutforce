import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const longName = "Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом";
const shortName = "А".repeat(64);
const baseWine = { winery: "Abrau Estates", year: 2024, image: "/catalog-assets/v2/images/long.webp", description: "Описание карточки.", imageVariants: [{ role: "thumbnail", path: "/catalog-assets/v2/images/long-160.webp", width: 160, height: 240, bytes: 1, mimeType: "image/webp", sha256: "a" }, { role: "card", path: "/catalog-assets/v2/images/long-640.webp", width: 640, height: 960, bytes: 1, mimeType: "image/webp", sha256: "b" }] };
const longWine = { ...baseWine, id: "long-card", name: longName };
const shortWine = { ...baseWine, id: "short-card", name: shortName };
const otherWine = { ...baseWine, id: "other-card", name: "Мерло" };
const response = (data: unknown) => ({ ok: true, json: async () => data });
afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function openCard(wine = longWine) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [wine], catalogVersion: "test-v2" })));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /По названию/i }));
  await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
  await user.click(await screen.findByRole("button", { name: new RegExp(wine.name) }));
  return user;
}

describe("FE-057 Option A wine-card contract", () => {
  it("DESIGN-023 uses the selected white hero and image surface without multiply", () => {
    const css = readFileSync("src/v2.css", "utf8");
    expect(css).toContain("#UI-007 .result-hero{background:#fff");
    expect(css).toContain("#UI-007 .result-hero>img,#UI-007 .result-hero>.missing-image");
    expect(css).toContain("mix-blend-mode:normal");
  });

  it("DESIGN-024 keeps Back and Save as named, pressed header controls and returns to catalog context", async () => {
    const user = await openCard();
    const save = screen.getByRole("button", { name: "Сохранить вино" });
    expect(save).toHaveAttribute("aria-pressed", "false");
    await user.click(save);
    expect(screen.getByRole("button", { name: "Удалить из сохранённых" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByLabelText(/Название вина/i)).toBeVisible();
    expect(screen.getByRole("button", { name: new RegExp(longName) })).toBeVisible();
  });

  it("DESIGN-025 stacks only names over 64 characters and retains responsive image fallback", async () => {
    await openCard(longWine);
    expect(document.querySelector(".result-hero")).toHaveClass("result-hero-long");
    const image = document.querySelector(".result-hero img")!;
    expect(image).toHaveAttribute("sizes", "160px");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: `Фото ${longName} недоступно` })).toBeVisible();
    cleanup();
    await openCard(shortWine);
    expect(document.querySelector(".result-hero")).not.toHaveClass("result-hero-long");
    expect(document.querySelector(".result-hero img")).toHaveAttribute("sizes", "(max-width: 360px) 96px, 128px");
  });

  it("DESIGN-026 keeps search rows in backend order with 84px leader and 72px normal images", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [longWine, otherWine], catalogVersion: "test-v2" })));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.type(screen.getByLabelText(/Название вина/i), "А");
    await user.click(screen.getByRole("button", { name: "Искать" }));
    const leader = await screen.findByAltText(`Фото вина: ${longName}`);
    const normal = screen.getByAltText("Фото вина: Мерло");
    expect(leader).toHaveAttribute("sizes", "84px");
    expect(normal).toHaveAttribute("sizes", "72px");
    const names = [...document.querySelectorAll(".candidate-list > button b")].map((node) => node.textContent);
    expect(names.slice(0, 2)).toEqual([longName, "Мерло"]);
  });
});
