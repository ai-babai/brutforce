import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const cabernet = {
  id: "cabernet",
  name: "Каберне Совиньон",
  winery: "Долина",
  year: 2023,
  image: "/assets/concept-bottle.png",
  description: "Красное вино.",
};
const merlot = {
  id: "merlot",
  name: "Мерло",
  winery: "Берег",
  year: 2022,
  image: "",
  description: "Мягкое вино.",
};
const catalog = { demo: true, candidates: [cabernet, merlot] };
const response = (data: unknown) => ({ ok: true, json: async () => data });

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const mockCatalog = () =>
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(catalog)));
const openCatalog = async () => {
  await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
  await userEvent.click(screen.getByRole("button", { name: "Открыть каталог" }));
};

describe("catalog navigation and saved wines", () => {
  it("UI-016 bottom navigation opens the catalog, filters it, and resets section scroll", async () => {
    mockCatalog();
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Основная навигация" });
    const content = document.querySelector(".app-content") as HTMLDivElement;
    expect(screen.getByRole("button", { name: "Сканер" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await openCatalog();
    expect(screen.getByRole("button", { name: "Поиск" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      await screen.findByRole("button", { name: /Каберне Совиньон/i }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /Мерло/i })).toBeVisible();
    await userEvent.type(screen.getByLabelText(/Название вина/i), "мерло");
    expect(
      screen.queryByRole("button", { name: /Каберне Совиньон/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Мерло/i })).toBeVisible();
    content.scrollTop = 480;
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(content.scrollTop).toBe(0);
    expect(nav).toBeVisible();
  });

  it("UI-022 bottom Scanner starts a fresh camera capture and falls back after a denial", async () => {
    const getUserMedia = vi.fn(() => new Promise<MediaStream>(() => {}));
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    const first = render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сканер" }));
    expect(await screen.findByLabelText(/Изображение с камеры/i)).toBeVisible();
    expect(getUserMedia).toHaveBeenCalledOnce();
    expect(
      screen.queryByRole("navigation", { name: "Основная навигация" }),
    ).not.toBeInTheDocument();
    first.unmount();
    render(<App simulatePermissionDenied />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(screen.getByRole("button", { name: "Сканер" }));
    expect(
      screen.getByRole("heading", { name: "Камера недоступна" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.click(screen.getByRole("button", { name: "Сканер" }));
    expect(
      screen.getByRole("heading", { name: "Камера недоступна" }),
    ).toBeVisible();
  });

  it("UI-017 saves one validated catalog snapshot and restores it after reload", async () => {
    mockCatalog();
    const first = render(<App />);
    await openCatalog();
    await userEvent.click(
      await screen.findByRole("button", { name: /Каберне Совиньон/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Сохранить вино" }),
    );
    expect(JSON.parse(localStorage.getItem("wine-demo-saved-v1")!)).toEqual([
      cabernet,
    ]);
    first.unmount();
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(
      screen.getByRole("button", { name: /Каберне Совиньон/i }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: /Каберне Совиньон/i }),
    );
    expect(
      screen.getByRole("heading", { name: "Каберне Совиньон" }),
    ).toBeVisible();
  });

  it("UI-018 removes a saved wine and returns to the useful empty state", async () => {
    localStorage.setItem("wine-demo-saved-v1", JSON.stringify([cabernet]));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Каберне Совиньон/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Удалить из сохранённых" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(
      screen.getByRole("heading", { name: "Пока ничего не сохранено" }),
    ).toBeVisible();
    expect(JSON.parse(localStorage.getItem("wine-demo-saved-v1")!)).toEqual([]);
  });

  it("UI-019 clears corrupt or duplicate saved snapshots without crashing", async () => {
    localStorage.setItem(
      "wine-demo-saved-v1",
      JSON.stringify([cabernet, cabernet]),
    );
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getByRole("status")).toHaveTextContent(/повреждён и очищен/i);
    expect(
      screen.getByRole("heading", { name: "Пока ничего не сохранено" }),
    ).toBeVisible();
    expect(localStorage.getItem("wine-demo-saved-v1")).toBeNull();
  });

  it("UI-020 leaving catalog aborts the request and a late response cannot change section", async () => {
    let resolve!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((done) => {
            resolve = done;
          }),
      ),
    );
    render(<App />);
    await openCatalog();
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    resolve(response(catalog));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Пока ничего не сохранено" }),
      ).toBeVisible(),
    );
    expect(screen.getByRole("button", { name: "Сохранённое" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.queryByRole("button", { name: /Каберне Совиньон/i }),
    ).not.toBeInTheDocument();
  });

  it("UI-021 reports storage failure and does not claim the wine was saved", async () => {
    mockCatalog();
    vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    render(<App />);
    await openCatalog();
    await userEvent.click(
      await screen.findByRole("button", { name: /Каберне Совиньон/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Сохранить вино" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      /Не удалось сохранить/i,
    );
    expect(
      screen.getByRole("button", { name: "Сохранить вино" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("UI-023 toggles the stable compact header save action", async () => {
    mockCatalog();
    render(<App />);
    await openCatalog();
    await userEvent.click(
      await screen.findByRole("button", { name: /Каберне Совиньон/i }),
    );
    const action = screen.getByRole("button", { name: "Сохранить вино" });
    expect(action).toHaveClass("save-header-action");
    expect(action).toHaveAttribute("aria-pressed", "false");
    expect(action).toHaveTextContent("Сохранить");
    await userEvent.click(action);
    const savedAction = screen.getByRole("button", {
      name: "Удалить из сохранённых",
    });
    expect(savedAction).toHaveClass("save-header-action");
    expect(savedAction).toHaveAttribute("aria-pressed", "true");
    expect(savedAction).toHaveTextContent("Сохранено");
    expect(document.querySelector("#UI-007>.save-action")).toBeNull();
    await userEvent.click(savedAction);
    expect(
      screen.getByRole("button", { name: "Сохранить вино" }),
    ).toHaveAttribute("aria-pressed", "false");
  });

  it("UI-024 submits the compact search field with its button and Enter", async () => {
    const expected = JSON.stringify({ scenario: "exact", query: "Каберне" });
    mockCatalog();
    const first = render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(screen.getByLabelText(/Название вина/i), "Каберне");
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/search"),
      ).toHaveLength(1),
    );
    expect(
      (
        vi
          .mocked(fetch)
          .mock.calls.find(([url]) => url === "/v1/search")![1] as RequestInit
      ).body,
    ).toBe(expected);
    first.unmount();
    mockCatalog();
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(
      screen.getByLabelText(/Название вина/i),
      "Каберне{enter}",
    );
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/search"),
      ).toHaveLength(1),
    );
    expect(
      (
        vi
          .mocked(fetch)
          .mock.calls.find(([url]) => url === "/v1/search")![1] as RequestInit
      ).body,
    ).toBe(expected);
  });

  it("returns from a catalog card to the same list position", async () => {
    mockCatalog();
    render(<App />);
    await openCatalog();
    const content = document.querySelector(".app-content") as HTMLDivElement;
    await screen.findByRole("button", { name: /Каберне Совиньон/i });
    content.scrollTop = 240;
    await userEvent.click(screen.getByRole("button", { name: /Каберне Совиньон/i }));
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(content.scrollTop).toBe(240);
    expect(screen.getByRole("button", { name: /Каберне Совиньон/i })).toBeVisible();
  });

  it("a saved card correction cannot reuse candidates from an older search", async () => {
    localStorage.setItem("wine-demo-saved-v1", JSON.stringify([cabernet]));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(screen.getByRole("button", { name: /Каберне Совиньон/i }));
    await userEvent.click(screen.getByRole("button", { name: /Не это вино/i }));
    expect(screen.getByRole("heading", { name: "Найдём вручную" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByRole("heading", { name: "Каберне Совиньон" })).toBeVisible();
  });
});
