import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const longName = "Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом";
const wine = {
  id: "long-card", name: longName, winery: "Abrau Estates", year: 2024,
  image: "/catalog-assets/v2/images/long.webp", description: "Описание карточки.",
  imageVariants: [
    { role: "thumbnail", path: "/catalog-assets/v2/images/long-160.webp", width: 160, height: 240, bytes: 1, mimeType: "image/webp", sha256: "a" },
    { role: "card", path: "/catalog-assets/v2/images/long-640.webp", width: 640, height: 960, bytes: 1, mimeType: "image/webp", sha256: "b" },
  ],
};
const response = (data: unknown) => ({ ok: true, json: async () => data });
afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function openCard() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [wine], catalogVersion: "test-v2" })));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /По названию/i }));
  await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
  await user.click(await screen.findByRole("button", { name: new RegExp(longName) }));
  return user;
}

describe("FE-057 Option A wine-card contract", () => {
  it("DESIGN-023 marks a title over 64 characters for a stacked hero without truncating it", async () => {
    await openCard();
    const hero = document.querySelector(".result-hero")!;
    expect(hero).toHaveClass("result-hero-long");
    expect(screen.getByRole("heading", { name: longName })).toBeVisible();
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

  it("DESIGN-025 keeps card image responsive dimensions and the existing fallback", async () => {
    await openCard();
    const image = document.querySelector(".result-hero img")!;
    expect(image).toHaveAttribute("src", wine.imageVariants[1].path);
    expect(image).toHaveAttribute("width", "640");
    expect(image).toHaveAttribute("height", "960");
    expect(image).toHaveAttribute("sizes", "160px");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: `Фото ${longName} недоступно` })).toBeVisible();
  });

  it("DESIGN-026 encodes Option A's white surface, contain bottle, and long-title stack", () => {
    const css = readFileSync("src/v2.css", "utf8");
    expect(css).toContain("#UI-007 .result-hero{background:#fff");
    expect(css).toContain("#UI-007 .result-hero.result-hero-long");
    expect(css).toContain("#UI-007 .result-hero img{height:200px;object-fit:contain");
    expect(css).not.toContain("#UI-007 .result-hero{mix-blend-mode:multiply");
  });
});
