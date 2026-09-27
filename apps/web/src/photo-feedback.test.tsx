import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const token = "11111111111111111111111111111111";
const wine = { id: "1", name: "Каберне", winery: "Фанагория", image: "/assets/concept-bottle.png", description: "Описание" };
const jsonResponse = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function photo() { return new File(["image"], "wine.jpg", { type: "image/jpeg" }); }
function receipt() { return { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-25T12:00:00Z", bytes: 5, mime: "image/jpeg", width: 20, height: 20 }; }

describe("public photo search without annotation controls", () => {
  it("keeps a recognized photo result usable without exposing feedback", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/v1/photos") return Promise.resolve(jsonResponse(receipt(), 201));
      if (url === "/v1/search") return Promise.resolve(jsonResponse({ demo: true, candidates: [wine], selectedId: wine.id, catalogVersion: "test-v2", modelVersion: "m1", feedbackToken: token }));
      if (url === "/v1/recommendations") return Promise.resolve(jsonResponse({ demo: true, candidates: [] }));
      throw new Error(`unexpected ${url} ${String(init?.method)}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:photo"), revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), photo());
    await userEvent.click(await screen.findByRole("button", { name: /Каберне/i }));
    expect(screen.getByRole("heading", { name: wine.name })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Разметить мою фотографию" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Подтвердить" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => url === "/v1/feedback")).toBe(false);
  });

  it("keeps the no-match recovery without offering feedback", async () => {
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      if (url === "/v1/photos") return Promise.resolve(jsonResponse(receipt(), 201));
      if (url === "/v1/search") return Promise.resolve(jsonResponse({ demo: true, candidates: [], catalogVersion: "test-v2", feedbackToken: token }));
      if (url.startsWith("/v2/catalog")) return Promise.resolve(jsonResponse({ demo: true, candidates: [wine], catalogVersion: "test-v2" }));
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:photo"), revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), photo());
    expect(await screen.findByRole("heading", { name: "Ничего не найдено" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Разметить мою фотографию" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Указать правильное вино" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Найти по названию" }));
    expect(await screen.findByLabelText(/Название вина/i)).toBeVisible();
    expect(fetchMock.mock.calls.some(([url]) => url === "/v1/feedback")).toBe(false);
  });
});
