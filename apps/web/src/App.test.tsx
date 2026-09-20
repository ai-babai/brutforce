import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const candidate = {
  id: "1",
  name: "Каберне Совиньон",
  winery: "Демо-винодельня",
  year: 2023,
  image: "/assets/concept-bottle.png",
  description: "Описание из демо.",
};
const exact = { demo: true, candidates: [candidate], selectedId: "1" };
const uncertain = {
  demo: true,
  candidates: [
    candidate,
    { ...candidate, id: "2", name: "Мерло", year: 2022, image: "" },
  ],
};
const receipt = {
  id: "0123456789abcdef0123456789abcdef",
  createdAt: "2026-09-19T09:00:00Z",
  bytes: 5,
  mime: "image/jpeg",
  width: 100,
  height: 100,
};
const response = (data: unknown, ok = true) => ({ ok, json: async () => data });

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function mock(data: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(data, ok)));
}
async function submitManual(query = "Каберне", user = userEvent.setup()) {
  await user.click(screen.getByRole("button", { name: /По названию/i }));
  await user.type(screen.getByLabelText(/Название вина/i), query);
  await user.click(screen.getByRole("button", { name: "Искать" }));
  return user;
}

describe("mobile behavior demo", () => {
  it("UI-001 to UI-002 starts live camera and separates camera from gallery", async () => {
    const stop = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi
          .fn()
          .mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    render(<App />);
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: /Сканировать вино/i }),
    );
    expect(await screen.findByText(/Наведите на этикетку/i)).toBeVisible();
    expect(screen.getByLabelText(/Изображение с камеры/i)).toBeVisible();
    expect(screen.getByLabelText(/Снять фотографию/i)).toHaveAttribute(
      "capture",
      "environment",
    );
    expect(screen.getByLabelText(/Загрузить фотографию/i)).not.toHaveAttribute(
      "capture",
    );
  });
  it("stops a camera stream that resolves after leaving UI-002", async () => {
    let resolveStream!: (stream: {
      getTracks: () => { stop: () => void }[];
    }) => void;
    const stop = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn(
          () =>
            new Promise((resolve) => {
              resolveStream = resolve;
            }),
        ),
      },
    });
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: /Сканировать вино/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    resolveStream({ getTracks: () => [{ stop }] });
    await waitFor(() => expect(stop).toHaveBeenCalledOnce());
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
  });
  it("UI-002 shutter captures a JPEG frame, uploads it, and stops the stream", async () => {
    const stop = vi.fn(),
      drawImage = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi
          .fn()
          .mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage,
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
      (callback) => callback(new Blob(["jpeg"], { type: "image/jpeg" })),
    );
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:camera"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(receipt))
        .mockResolvedValueOnce(response(exact)),
    );
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: /Сканировать вино/i }),
    );
    const video = await screen.findByLabelText(/Изображение с камеры/i);
    Object.defineProperty(video, "videoWidth", { value: 640 });
    Object.defineProperty(video, "videoHeight", { value: 480 });
    await userEvent.click(screen.getByRole("button", { name: "Снять фото" }));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Каберне Совиньон" }),
      ).toBeVisible(),
    );
    expect(drawImage).toHaveBeenCalled();
    expect(stop).toHaveBeenCalled();
    expect(
      (vi.mocked(fetch).mock.calls[0][1] as RequestInit).body,
    ).toBeInstanceOf(FormData);
  });
  it("UI-003 offers fallbacks after permission denial", async () => {
    render(<App simulatePermissionDenied />);
    await userEvent.click(
      screen.getByRole("button", { name: /Сканировать вино/i }),
    );
    expect(
      screen.getByRole("heading", { name: "Камера недоступна" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /Выбрать фото/i })).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Найти по названию/i }),
    ).toBeVisible();
  });
  it("UI-003A explains permission recovery and retains gallery fallback", async () => {
    render(<App simulatePermissionDenied />);
    await userEvent.click(
      screen.getByRole("button", { name: /Сканировать вино/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Как разрешить камеру/i }),
    );
    expect(
      screen.getByRole("heading", { name: /Проверьте доступ/i }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Вернуться к камере/i }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /Выбрать фото/i })).toBeVisible();
  });
  it("upload preview sends multipart receipt into search and reaches UI-007", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(receipt))
        .mockResolvedValueOnce(response(exact)),
    );
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:label-photo"),
      revokeObjectURL: vi.fn(),
    });
    render(<App />);
    const file = new File(["image"], "label.jpg", { type: "image/jpeg" });
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      file,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Каберне Совиньон" }),
      ).toBeVisible(),
    );
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls[0][0]).toBe("/v1/photos");
    expect((calls[0][1] as RequestInit).body).toBeInstanceOf(FormData);
    expect(calls[1][0]).toBe("/v1/search");
    expect((calls[1][1] as RequestInit).body).toBe(
      JSON.stringify({ scenario: "exact", photoId: receipt.id }),
    );
    expect(screen.getAllByText("2023")[0]).toBeVisible();
  });
  it("UI-011 rejects a non-image before API use", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["text"], "notes.txt", { type: "text/plain" }),
      { applyAccept: false },
    );
    expect(
      screen.getByRole("heading", { name: "Нужно изображение" }),
    ).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("UI-011 explains the accepted formats after a server photo rejection", async () => {
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:rejected"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 415,
        json: async () => ({ error: { code: "invalid_photo" } }),
      }),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["image"], "broken.jpg", { type: "image/jpeg" }),
    );
    expect(await screen.findByText(/JPEG, PNG или GIF.*10 МБ/i)).toBeVisible();
  });
  it("UI-008 keeps the catalog hidden until the user asks for it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(exact)));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /По названию/i }));
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Каберне Совиньон/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Открыть каталог" }));
    expect(await screen.findByRole("button", { name: /Каберне Совиньон/i })).toBeVisible();
  });
  it("UI-004/005 cancellation returns home and keeps a photo only for explicit resume or deletion", async () => {
    let searches = 0;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:retained"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        url === "/v1/photos"
          ? Promise.resolve(response(receipt))
          : ++searches === 1
            ? new Promise(() => {})
            : Promise.resolve(response(exact)),
      ),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["photo"], "wine.jpg", { type: "image/jpeg" }),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: /Отменить поиск/i }));
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Продолжить поиск/i }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /Удалить фото/i })).toBeVisible();
    expect(searches).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: /Удалить фото/i }));
    expect(
      screen.queryByRole("button", { name: /Продолжить поиск/i }),
    ).not.toBeInTheDocument();
  });
  it("UI-005 ignores a late response after cancellation and resumes only on request", async () => {
    let resolveFetch!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve) => {
            resolveFetch = resolve;
          }),
      ),
    );
    render(<App />);
    await submitManual();
    await userEvent.click(
      screen.getByRole("button", { name: /Отменить поиск/i }),
    );
    resolveFetch(response(exact));
    await Promise.resolve();
    await Promise.resolve();
    expect(screen.getByRole("heading", { name: /Какое вино/i })).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Каберне Совиньон" }),
    ).not.toBeInTheDocument();
  });
  it("UI-005 retry preserves scenario and query", async () => {
    let searches = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        url === "/v1/catalog"
          ? Promise.resolve(response(uncertain))
          : ++searches === 1
            ? new Promise(() => {})
            : Promise.resolve(response(uncertain)),
      ),
    );
    render(<App initialScenario="uncertain" />);
    await submitManual("Мерло");
    await userEvent.click(
      screen.getByRole("button", { name: /Отменить поиск/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Продолжить поиск/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /несколько похожих/i }),
      ).toBeVisible(),
    );
    const calls = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => url === "/v1/search");
    expect(calls).toHaveLength(2);
    expect((calls[0][1] as RequestInit).body).toBe(
      JSON.stringify({ scenario: "uncertain", query: "Мерло" }),
    );
    expect((calls[1][1] as RequestInit).body).toBe(
      (calls[0][1] as RequestInit).body,
    );
  });
  it("UI-005 retry reuses a completed upload receipt", async () => {
    let searches = 0;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:photo"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        url === "/v1/photos"
          ? Promise.resolve(response(receipt))
          : ++searches === 1
            ? new Promise(() => {})
            : Promise.resolve(response(exact)),
      ),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["photo"], "wine.jpg", { type: "image/jpeg" }),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    await userEvent.click(
      screen.getByRole("button", { name: /Отменить поиск/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Продолжить поиск/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Каберне Совиньон" }),
      ).toBeVisible(),
    );
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.filter(([url]) => url === "/v1/photos")).toHaveLength(1);
    const searchCalls = calls.filter(([url]) => url === "/v1/search");
    expect(searchCalls).toHaveLength(2);
    expect((searchCalls[1][1] as RequestInit).body).toBe(
      (searchCalls[0][1] as RequestInit).body,
    );
  });
  it("UI-006 manual candidates do not invent an original photo", async () => {
    mock(uncertain);
    render(<App initialScenario="uncertain" />);
    await submitManual("Мерло");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /несколько похожих/i }),
      ).toBeVisible(),
    );
    expect(
      screen.queryByRole("button", { name: /Открыть исходную фотографию/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Фото Мерло отсутствует/i }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Мерло/i }));
    expect(screen.getByRole("heading", { name: "Мерло" })).toBeVisible();
  });
  it("UI-007 exposes the simulated source description after manual candidate choice", async () => {
    mock(exact);
    render(<App />);
    await submitManual();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /несколько похожих/i }),
      ).toBeVisible(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Каберне Совиньон/i }),
    );
    await userEvent.click(screen.getByRole("tab", { name: "Источник" }));
    expect(screen.getByText(/карточка создана для прототипа/i)).toBeVisible();
    expect(
      screen.getByRole("link", { name: /Открыть платформу/i }),
    ).toHaveAttribute("href", "https://vino-svoe.ru/");
  });
  it("UI-008 does not send an empty manual query and keeps camera entry available", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(exact)));
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /По названию/i }));
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    expect(
      vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/search"),
    ).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: /Сканировать этикетку/i }),
    ).toBeVisible();
  });
  it("UI-008 sends none and UI-009 offers recovery", async () => {
    mock({ demo: true, candidates: [] });
    render(<App initialScenario="none" />);
    await submitManual("Редкое вино");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Вино не найдено" }),
      ).toBeVisible(),
    );
    expect(fetch).toHaveBeenCalledWith(
      "/v1/search",
      expect.objectContaining({
        body: JSON.stringify({ scenario: "none", query: "Редкое вино" }),
      }),
    );
    expect(
      screen.getByRole("button", { name: "Изменить запрос" }),
    ).toBeVisible();
  });
  it("UI-010 rejects selectedId absent from candidates", async () => {
    mock({ ...exact, selectedId: "missing" });
    render(<App />);
    await submitManual();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Сервис временно недоступен" }),
      ).toBeVisible(),
    );
  });
  it("UI-026 preview returns to its settled async origin instead of restoring stale loading", async () => {
    let resolveSearch!: (value: ReturnType<typeof response>) => void;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:preview"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        url === "/v1/photos"
          ? Promise.resolve(response(receipt))
          : new Promise((resolve) => {
              resolveSearch = resolve;
            }),
      ),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["photo"], "wine.jpg", { type: "image/jpeg" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Открыть исходную фотографию/i }),
    );
    resolveSearch(response(exact));
    await Promise.resolve();
    await Promise.resolve();
    await userEvent.click(
      screen.getByRole("button", { name: /Закрыть фотографию/i }),
    );
    expect(
      screen.getByRole("heading", { name: "Каберне Совиньон" }),
    ).toBeVisible();
  });
  it("UI-027 manual query, candidates, and correction preserve their return context", async () => {
    mock(uncertain);
    render(<App initialScenario="uncertain" />);
    await submitManual("Мерло");
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /несколько похожих/i }),
      ).toBeVisible(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Каберне Совиньон/i }),
    );
    expect(
      screen.getByRole("heading", { name: "Каберне Совиньон" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "Описание" }));
    await userEvent.click(screen.getByRole("button", { name: /Не это вино/i }));
    await userEvent.click(
      screen.getByRole("button", { name: "Ни одно не подходит" }),
    );
    expect(
      screen.getByRole("heading", { name: "Найдём вручную" }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Искать" }));
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /несколько похожих/i }),
      ).toBeVisible(),
    );
    await userEvent.click(screen.getByRole("button", { name: /Мерло/i }));
    expect(screen.getByRole("heading", { name: "Мерло" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(
      screen.getByRole("heading", { name: /несколько похожих/i }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(
      screen.getByRole("heading", { name: "Найдём вручную" }),
    ).toBeVisible();
    expect(screen.getByLabelText(/Название вина/i)).toHaveValue("Мерло");
    await userEvent.click(screen.getByRole("button", { name: "Назад" }));
    expect(
      screen.getByRole("heading", { name: "Каберне Совиньон" }),
    ).toBeVisible();
    expect(screen.getByRole("tab", { name: "Описание" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
  it("UI-028 distinguishes network and server failures and retries a retained receipt", async () => {
    let searches = 0;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:error"),
      revokeObjectURL: vi.fn(),
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        url === "/v1/photos"
          ? Promise.resolve(response(receipt))
          : ++searches === 1
            ? Promise.reject(new TypeError("Failed to fetch"))
            : Promise.resolve(response(exact)),
      ),
    );
    render(<App />);
    await userEvent.upload(
      screen.getByLabelText(/Загрузить фотографию/i),
      new File(["photo"], "wine.jpg", { type: "image/jpeg" }),
    );
    await waitFor(() =>
      expect(screen.getByText(/Проверьте подключение/i)).toBeVisible(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Повторить запрос/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Каберне Совиньон" }),
      ).toBeVisible(),
    );
    expect(
      vi.mocked(fetch).mock.calls.filter(([url]) => url === "/v1/photos"),
    ).toHaveLength(1);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );
    render(<App />);
    await submitManual("Сервер");
    await waitFor(() =>
      expect(screen.getByText(/Сервис временно недоступен/i)).toBeVisible(),
    );
  });
});
