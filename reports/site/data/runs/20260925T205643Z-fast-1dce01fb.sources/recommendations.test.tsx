import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const selected = {
  id: "cabernet",
  name: "Каберне Совиньон",
  winery: "Демо-винодельня",
  year: 2023,
  image: "/assets/concept-bottle.png",
  description: "Описание из демо.",
};
const recommendation = {
  ...selected,
  id: "merlot",
  name: "Мерло",
  year: 2022,
};
const response = (data: unknown, ok = true) => ({ ok, json: async () => data });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function openCard() {
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /По названию/i }));
  await user.type(screen.getByLabelText(/Название вина/i), "Каберне");
  await user.click(screen.getByRole("button", { name: "Искать" }));
  await screen.findByRole("button", { name: /Каберне Совиньон/i });
  await user.click(screen.getByRole("button", { name: /Каберне Совиньон/i }));
  await screen.findByRole("heading", { name: "Каберне Совиньон" });
  return user;
}

function mockApi(recommendationResponse: unknown) {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.startsWith("/v2/catalog")
        ? response({ demo: true, candidates: [selected], catalogVersion: "demo-v2" })
        : url === "/v1/recommendations"
          ? response(recommendationResponse)
          : response({ demo: true, candidates: [selected] }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("wine-card recommendations", () => {
  it("REC001 requests recommendations for the selected wine and labels them separately from search candidates", async () => {
    const fetchMock = mockApi({
      demo: true,
      candidates: [recommendation, { ...recommendation, id: "pinot", name: "Пино Нуар" }],
    });
    await openCard();
    expect(await screen.findByText("Вам также может подойти")).toBeVisible();
    expect(screen.getByText("Мерло")).toBeVisible();
    expect(screen.getAllByText("Наиболее похожее")).toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/recommendations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ wineId: "cabernet", limit: 3 }),
      }),
    );
  });

  it("REC002 keeps the wine card intact when recommendations are empty", async () => {
    mockApi({ demo: true, candidates: [] });
    await openCard();
    expect(await screen.findByText("Пока нет рекомендаций для этой карточки.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Каберне Совиньон" })).toBeVisible();
  });

  it("REC003 exposes retry after a recommendation failure without replacing the wine card", async () => {
    let recommendations = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(
          url.startsWith("/v2/catalog")
            ? response({ demo: true, candidates: [selected], catalogVersion: "demo-v2" })
            : url === "/v1/recommendations"
              ? ++recommendations === 1
                ? response({}, false)
                : response({ demo: true, candidates: [recommendation] })
              : response({ demo: true, candidates: [selected] }),
        ),
      ),
    );
    const user = await openCard();
    expect(await screen.findByText("Не удалось загрузить рекомендации.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Каберне Совиньон" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Повторить рекомендации" }));
    expect(await screen.findByText("Мерло")).toBeVisible();
  });

  it("REC004 aborts an obsolete request and ignores its late response after navigation", async () => {
    let resolveRecommendations!: (value: ReturnType<typeof response>) => void;
    const fetchMock = vi.fn((url: string) =>
      url === "/v1/recommendations"
        ? new Promise((resolve) => {
            resolveRecommendations = resolve;
          })
        : Promise.resolve(
            url.startsWith("/v2/catalog")
              ? response({ demo: true, candidates: [selected], catalogVersion: "demo-v2" })
              : response({ demo: true, candidates: [selected] }),
          ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = await openCard();
    await user.click(screen.getByRole("button", { name: "Поиск" }));
    resolveRecommendations(response({ demo: true, candidates: [recommendation] }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Найдём по названию" })).toBeVisible(),
    );
    expect(screen.queryByText("Вам также может подойти")).not.toBeInTheDocument();
    const [, request] = fetchMock.mock.calls.find(
      ([url]) => url === "/v1/recommendations",
    )! as unknown as [string, RequestInit];
    expect((request.signal as AbortSignal).aborted).toBe(true);
  });

  it("REC005 opens an explicitly selected recommendation and requests once for its new wine", async () => {
    const fetchMock = mockApi({ demo: true, candidates: [recommendation] });
    const user = await openCard();
    await screen.findByText("Мерло");
    const content = document.querySelector(".app-content") as HTMLDivElement;
    content.scrollTop = 246;
    await user.click(screen.getByRole("button", { name: /Мерло/i }));
    expect(screen.getByRole("heading", { name: "Мерло" })).toBeVisible();
    expect(content.scrollTop).toBe(0);
    const calls = fetchMock.mock.calls.filter(([url]) => url === "/v1/recommendations");
    expect(calls).toHaveLength(2);
    expect((calls[1] as unknown as [string, RequestInit])[1].body).toBe(
      JSON.stringify({ wineId: "merlot", limit: 3 }),
    );
  });
});
