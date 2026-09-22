import { readFileSync } from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const longName = "Коллекционное игристое вино из виноградников южного склона с выдержкой в бутылке и редким купажом";
const otherName = "Мерло";
const baseWine = {
  winery: "Abrau Estates",
  year: 2024,
  image: "/catalog-assets/v2/images/long.webp",
  description: "Описание карточки.",
  imageVariants: [
    { role: "thumbnail", path: "/catalog-assets/v2/images/long-160.webp", width: 160, height: 240, bytes: 1, mimeType: "image/webp", sha256: "a" },
    { role: "card", path: "/catalog-assets/v2/images/long-640.webp", width: 640, height: 960, bytes: 1, mimeType: "image/webp", sha256: "b" },
  ],
};
const longWine = { ...baseWine, id: "long-card", name: longName };
const otherWine = { ...baseWine, id: "other-card", name: otherName };
const response = (data: unknown) => ({ ok: true, json: async () => data });

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function openCard(wine = longWine) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [wine], catalogVersion: "test-v2" })));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /По названию/i }));
  await user.click(screen.getByRole("button", { name: /Открыть каталог/i }));
  await user.click(await screen.findByRole("button", { name: new RegExp(wine.name) }));
  return user;
}

describe("FE-057 revised wine-card contract", () => {
  it("DESIGN-023 keeps the warm app palette while using white for the revised hero and result tiles", () => {
    const css = readFileSync("src/v2.css", "utf8");
    expect(css).toContain("--paper:#fefdfa");
    expect(css).toMatch(/#UI-007\s*\.result-hero\s*\{[^}]*min-height:\s*254px[^}]*background:\s*#fff/);
    expect(css).toMatch(/#UI-007\s*\.result-hero>img[^}]*height:\s*216px[^}]*object-fit:\s*contain/);
    expect(css).toMatch(/\.candidate-list\s+button[^}]*background:\s*#fff/);
    expect(css).toMatch(/\.candidate-list\s+img[^}]*background:\s*#fff/);
    expect(css).not.toMatch(/mix-blend-mode:\s*multiply/);
  });

  it("DESIGN-024 retains named Back and Save controls and returns to the catalog context", async () => {
    const user = await openCard();
    const save = screen.getByRole("button", { name: "Сохранить вино" });
    expect(save).toHaveAttribute("aria-pressed", "false");
    await user.click(save);
    expect(screen.getByRole("button", { name: "Удалить из сохранённых" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByLabelText(/Название вина/i)).toBeVisible();
    expect(screen.getByRole("button", { name: new RegExp(longName) })).toBeVisible();
  });

  it("DESIGN-025 keeps a complete long title in the existing hero and retains the card image fallback", async () => {
    await openCard();
    const hero = document.querySelector(".result-hero")!;
    expect(screen.getByRole("heading", { name: longName })).toBeVisible();
    expect(hero).not.toHaveClass("result-hero-long");
    const image = hero.querySelector("img")!;
    expect(image).toHaveAttribute("sizes", "(min-width: 1024px) 180px, 44vw");
    fireEvent.error(image);
    expect(screen.getByRole("img", { name: `Фото ${longName} недоступно` })).toBeVisible();
  });

  it("DESIGN-026 keeps backend order and the original leader and row image sizes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ demo: false, candidates: [longWine, otherWine], catalogVersion: "test-v2" })));
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /По названию/i }));
    await user.type(screen.getByLabelText(/Название вина/i), "А");
    await user.click(screen.getByRole("button", { name: "Искать" }));
    const leader = await screen.findByAltText(`Фото вина: ${longName}`);
    const normal = screen.getByAltText(`Фото вина: ${otherName}`);
    expect(leader).toHaveAttribute("sizes", "76px");
    expect(normal).toHaveAttribute("sizes", "56px");
    const names = [...document.querySelectorAll(".candidate-list > button b")].map((node) => node.textContent);
    expect(names.slice(0, 2)).toEqual([longName, otherName]);
  });
});
