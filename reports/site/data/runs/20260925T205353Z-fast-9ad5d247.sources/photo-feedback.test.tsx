import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const token = "11111111111111111111111111111111";
const wine = { id: "1", name: "Каберне", winery: "Фанагория", image: "/assets/concept-bottle.png", description: "Описание" };
const other = { ...wine, id: "2", name: "Мерло" };
const jsonResponse = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function photo() { return new File(["image"], "wine.jpg", { type: "image/jpeg" }); }
function receipt() { return { id: "0123456789abcdef0123456789abcdef", createdAt: "2026-09-25T12:00:00Z", bytes: 5, mime: "image/jpeg", width: 20, height: 20 }; }

describe("photo feedback", () => {
  it("FB-001 confirms the displayed photo result and shows a durable receipt", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === "/v1/photos") return Promise.resolve(jsonResponse(receipt(), 201));
      if (url === "/v1/search") return Promise.resolve(jsonResponse({ demo: true, candidates: [wine], selectedId: wine.id, catalogVersion: "test-v2", modelVersion: "m1", feedbackToken: token }));
      if (url === "/v1/recommendations") return Promise.resolve(jsonResponse({ demo: true, candidates: [] }));
      if (url === "/v1/feedback") return Promise.resolve(jsonResponse({ feedbackId: "22222222222222222222222222222222", createdAt: "2026-09-25T12:01:00Z", reviewStatus: "pending_review", duplicate: false }, 201));
      throw new Error(`unexpected ${url} ${String(init?.method)}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:photo"), revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), photo());
    await userEvent.click(await screen.findByRole("button", { name: /Каберне/i }));
    expect(await screen.findByRole("button", { name: "Подтвердить" })).toBeVisible();
    await userEvent.type(screen.getByLabelText(/Комментарий/i), "Это тот же винтаж");
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText("Разметка сохранена")).toBeVisible();
    const feedbackCall = fetchMock.mock.calls.find(([url]) => url === "/v1/feedback");
    const body = JSON.parse(String((feedbackCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({ feedbackToken: token, decision: "confirm", displayedWineId: wine.id, comment: "Это тот же винтаж" });
    expect(body.idempotencyKey).toMatch(/^[a-f0-9]{32}$/);
  });

  it("FB-002 FB-004 requires an explicit different SKU before saving a correction", async () => {
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      if (url === "/v1/photos") return Promise.resolve(jsonResponse(receipt(), 201));
      if (url === "/v1/search") return Promise.resolve(jsonResponse({ demo: true, candidates: [wine], selectedId: wine.id, catalogVersion: "test-v2", feedbackToken: token }));
      if (url === "/v1/recommendations") return Promise.resolve(jsonResponse({ demo: true, candidates: [] }));
      if (url.startsWith("/v2/catalog")) return Promise.resolve(jsonResponse({ demo: true, candidates: [other], catalogVersion: "test-v2" }));
      if (url === "/v1/feedback") return Promise.resolve(jsonResponse({ feedbackId: "33333333333333333333333333333333", createdAt: "2026-09-25T12:02:00Z", reviewStatus: "pending_review", duplicate: false }, 201));
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:photo"), revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), photo());
    await userEvent.click(await screen.findByRole("button", { name: /Каберне/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Нет, это другое вино" }));
    const save = await screen.findByRole("button", { name: "Сохранить исправление" });
    expect(save).toBeDisabled();
    await userEvent.click(await screen.findByRole("button", { name: /Мерло/i }));
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(screen.getByText("Разметка сохранена")).toBeVisible());
    const feedbackCall = fetchMock.mock.calls.find(([url]) => url === "/v1/feedback");
    const body = JSON.parse(String((feedbackCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({ decision: "correct", displayedWineId: wine.id, correctWineId: other.id });
  });

  it("FB-011 lets a user identify the correct SKU after a model no-match", async () => {
    const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
      if (url === "/v1/photos") return Promise.resolve(jsonResponse(receipt(), 201));
      if (url === "/v1/search") return Promise.resolve(jsonResponse({ demo: true, candidates: [], catalogVersion: "test-v2", feedbackToken: token }));
      if (url.startsWith("/v2/catalog")) return Promise.resolve(jsonResponse({ demo: true, candidates: [wine], catalogVersion: "test-v2" }));
      if (url === "/v1/feedback") return Promise.resolve(jsonResponse({ feedbackId: "44444444444444444444444444444444", createdAt: "2026-09-25T12:03:00Z", reviewStatus: "pending_review", duplicate: false }, 201));
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:photo"), revokeObjectURL: vi.fn() });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/Загрузить фотографию этикетки/i), photo());
    await userEvent.click(await screen.findByRole("button", { name: "Указать правильное вино" }));
    await userEvent.click(await screen.findByRole("button", { name: /Каберне/i }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить разметку" }));
    expect(await screen.findByText("Разметка сохранена")).toBeVisible();
    const feedbackCall = fetchMock.mock.calls.find(([url]) => url === "/v1/feedback");
    const body = JSON.parse(String((feedbackCall?.[1] as RequestInit).body));
    expect(body).toMatchObject({ decision: "correct", correctWineId: wine.id });
    expect(body).not.toHaveProperty("displayedWineId");
  });
});
