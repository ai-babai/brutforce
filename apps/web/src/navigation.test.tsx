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
const catalog = { demo: true, candidates: [cabernet, merlot], catalogVersion: "demo-v2" };
const receipt = {
  id: "0123456789abcdef0123456789abcdef",
  createdAt: "2026-09-20T12:00:00Z",
  bytes: 5,
  mime: "image/jpeg",
  width: 100,
  height: 100,
};
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
  it("UI-016 bottom navigation opens the catalog, searches on the server, and resets section scroll", async () => {
    mockCatalog();
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "Основная навигация" });
    const content = document.querySelector(".app-content") as HTMLDivElement;
    expect(screen.getByRole("button", { name: "Главная" })).toHaveAttribute(
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
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenLastCalledWith(
      "/v2/catalog?limit=24&cursor=&q=%D0%BC%D0%B5%D1%80%D0%BB%D0%BE", expect.any(Object),
    ));
    expect(screen.getByText("Наиболее похожее")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    await userEvent.clear(screen.getByLabelText(/Название вина/i));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenLastCalledWith(
      "/v2/catalog?limit=24&cursor=&q=", expect.any(Object),
    ));
    expect(screen.queryByText("Наиболее похожее")).not.toBeInTheDocument();
    content.scrollTop = 480;
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(content.scrollTop).toBe(0);
    expect(screen.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
  });

  it("UI-022 bottom Home returns to the start screen without starting camera capture", async () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    localStorage.setItem("wine-demo-saved-v1", JSON.stringify([cabernet]));
    mockCatalog();
    render(<App />);
    await openCatalog();
    await userEvent.click(screen.getByRole("button", { name: "Главная" }));
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(getUserMedia).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    expect(screen.getByRole("button", { name: /Каберне Совиньон/i })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(screen.getByLabelText(/Название вина/i), "Мерло");
    await userEvent.click(screen.getByRole("button", { name: "Главная" }));
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    expect(screen.getByLabelText(/Название вина/i)).toHaveValue("Мерло");
  });

  it("UI-022 explicit scan CTA starts camera capture and retains denial fallback", async () => {
    const getUserMedia = vi.fn(() => new Promise<MediaStream>(() => {}));
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    const first = render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /Сканировать вино/i }));
    expect(await screen.findByLabelText(/Изображение с камеры/i)).toBeVisible();
    expect(getUserMedia).toHaveBeenCalledOnce();
    first.unmount();
    render(<App simulatePermissionDenied />);
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(screen.getByRole("button", { name: "Главная" }));
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Сканировать вино/i }));
    expect(
      screen.getByRole("heading", { name: "Камера недоступна" }),
    ).toBeVisible();
  });

  it("UI-022 keeps a completed scan photo when Home opens without camera", async () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:retained-photo"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(receipt))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            demo: true,
            candidates: [cabernet],
            selectedId: cabernet.id,
          }),
        }),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["photo"], "wine.jpg", { type: "image/jpeg" }),
    );
    expect(
      await screen.findByRole("heading", { name: cabernet.name }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Главная" }));
    expect(
      screen.getByRole("img", { name: "Загруженная фотография этикетки" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Продолжить поиск" })).toBeVisible();
    expect(getUserMedia).not.toHaveBeenCalled();
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

  it("CAT002 submits the compact search field with its button and Enter", async () => {
    const url = "/v2/catalog?limit=24&cursor=&q=%D0%9A%D0%B0%D0%B1%D0%B5%D1%80%D0%BD%D0%B5";
    mockCatalog();
    const first = render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(screen.getByLabelText(/Название вина/i), "Каберне");
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(url, expect.any(Object)));
    first.unmount();
    mockCatalog();
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(screen.getByLabelText(/Название вина/i), "Каберне{enter}");
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(url, expect.any(Object)));
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
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(catalog)));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Поиск" }));
    await userEvent.type(screen.getByLabelText(/Название вина/i), "Мерло");
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    await screen.findByRole("heading", { name: /несколько похожих/i });
    await userEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
    await userEvent.click(screen.getByRole("button", { name: /Каберне Совиньон/i }));
    await userEvent.click(screen.getByRole("button", { name: /Не это вино/i }));
    expect(screen.getByRole("heading", { name: "Найдём вручную" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(screen.getByRole("heading", { name: "Каберне Совиньон" })).toBeVisible();
  });
});
