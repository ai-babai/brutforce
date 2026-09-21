import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { inflateSync } from "node:zlib";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { InstallApp } from "./InstallApp";
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const mode = (standalone: boolean) =>
  vi.stubGlobal("matchMedia", () => ({ matches: standalone }));
function offer(outcome = "dismissed", reject = false) {
  const prompt = reject
    ? vi.fn().mockRejectedValue(new Error("unavailable"))
    : vi.fn().mockResolvedValue(undefined);
  const event = Object.assign(
    new Event("beforeinstallprompt", { cancelable: true }),
    { prompt, userChoice: Promise.resolve({ outcome }) },
  );
  act(() => {
    window.dispatchEvent(event);
  });
  return prompt;
}
it("UI-012 ordinary browser remains usable without installation support", () => {
  mode(false);
  render(<App />);
  expect(
    screen.getByRole("button", { name: /Сканировать вино/ }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Установить приложение" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "По названию" }));
  expect(screen.getByLabelText(/Название вина/)).toBeVisible();
});
it("UI-013 installation only opens on click; dismissal preserves the web journey", async () => {
  mode(false);
  render(<App />);
  const prompt = offer();
  expect(prompt).not.toHaveBeenCalled();
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: "Установить приложение" }),
    );
  });
  expect(prompt).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("button", { name: /Сканировать вино/ }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Установить приложение" }),
  ).not.toBeInTheDocument();
});
it("UI-013 refused browser install prompt does not break the page", async () => {
  mode(false);
  render(<InstallApp />);
  offer("dismissed", true);
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: "Установить приложение" }),
    );
  });
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("UI-014 standalone exposes the same application without an install offer", () => {
  mode(true);
  render(<App />);
  offer();
  expect(
    screen.queryByRole("button", { name: "Установить приложение" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "По названию" }));
  expect(screen.getByLabelText(/Название вина/)).toBeVisible();
});
it("UI-014 successful installation removes the offer", () => {
  mode(false);
  render(<InstallApp />);
  offer();
  act(() => {
    window.dispatchEvent(new Event("appinstalled"));
  });
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("ICON-001 lists versioned selected-icon PNGs in manifest, favicon, and Apple metadata", () => {
  const manifest = JSON.parse(
    readFileSync("public/manifest.webmanifest", "utf8"),
  );
  expect(manifest.icons).toEqual(
    expect.arrayContaining([
      {
        src: "/assets/icon-24-any-v1-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/assets/icon-24-any-v1-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/assets/icon-24-maskable-v1-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/assets/icon-24-maskable-v1-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ]),
  );
  const html = new DOMParser().parseFromString(
    readFileSync("index.html", "utf8"),
    "text/html",
  );
  const metadata = [
    ...manifest.icons.map(
      (icon: { src: string; sizes: string; type: string }) => ({
        src: icon.src,
        sizes: icon.sizes,
        type: icon.type,
      }),
    ),
    {
      src: "/assets/icon-24-favicon-v1-32.png",
      sizes: "32x32",
      type: "image/png",
      rel: "icon",
    },
    {
      src: "/assets/icon-24-favicon-v1-48.png",
      sizes: "48x48",
      type: "image/png",
      rel: "icon",
    },
    {
      src: "/assets/icon-24-apple-v1-180.png",
      sizes: "180x180",
      type: undefined,
      rel: "apple-touch-icon",
    },
  ];
  for (const icon of metadata) {
    if ("rel" in icon) {
      const link = html.querySelector(`link[href="${icon.src}"]`);
      expect(link?.getAttribute("rel")).toBe(icon.rel);
      expect(link?.getAttribute("sizes")).toBe(icon.sizes);
      expect(link?.getAttribute("type")).toBe(icon.type ?? null);
    }
    const bytes = readFileSync("public" + icon.src);
    expect(bytes.subarray(1, 4).toString()).toBe("PNG");
    const size = Number(icon.sizes.split("x")[0]);
    expect(bytes.readUInt32BE(16)).toBe(size);
    expect(bytes.readUInt32BE(20)).toBe(size);
  }
});

function rgbPixels(file: string) {
  const bytes = readFileSync(file),
    chunks: Buffer[] = [];
  let at = 8,
    width = 0,
    height = 0,
    depth = 0,
    type = 0,
    interlace = 0;
  while (at < bytes.length) {
    const length = bytes.readUInt32BE(at),
      name = bytes.subarray(at + 4, at + 8).toString(),
      data = bytes.subarray(at + 8, at + 8 + length);
    if (name === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      depth = data[8];
      type = data[9];
      interlace = data[12];
    }
    if (name === "IDAT") chunks.push(data);
    at += length + 12;
  }
  expect([depth, type, interlace]).toEqual([8, 2, 0]);
  const raw = inflateSync(Buffer.concat(chunks)),
    stride = width * 3,
    output = Buffer.alloc(stride * height);
  expect(raw).toHaveLength(height * (stride + 1));
  let input = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[input++],
      row = output.subarray(y * stride, (y + 1) * stride);
    expect(filter).toBeLessThanOrEqual(4);
    for (let x = 0; x < stride; x++) {
      const value = raw[input++],
        left = x >= 3 ? row[x - 3] : 0,
        up = y ? output[(y - 1) * stride + x] : 0,
        upLeft = y && x >= 3 ? output[(y - 1) * stride + x - 3] : 0;
      let base = 0;
      if (filter === 1) base = left;
      if (filter === 2) base = up;
      if (filter === 3) base = Math.floor((left + up) / 2);
      if (filter === 4) {
        const p = left + up - upLeft,
          pa = Math.abs(p - left),
          pb = Math.abs(p - up),
          pc = Math.abs(p - upLeft);
        base = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
      }
      row[x] = (value + base) & 255;
    }
  }
  return { width, height, output };
}
function maskBounds(size: number) {
  const image = rgbPixels(`public/assets/icon-24-maskable-v1-${size}.png`),
    background = Array.from(image.output.subarray(0, 3));
  let minX = size,
    minY = size,
    maxX = -1,
    maxY = -1;
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const offset = (y * size + x) * 3;
      if (background.some((value, i) => image.output[offset + i] !== value)) {
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  return { minX, minY, maxX, maxY };
}
it("ICON-002 keeps substantial maskable art inside the conservative 40% safe-circle radius", () => {
  for (const size of [192, 512]) {
    const { minX, minY, maxX, maxY } = maskBounds(size);
    expect(maxX).toBeGreaterThanOrEqual(minX);
    expect(maxY).toBeGreaterThanOrEqual(minY);
    expect(maxX - minX + 1).toBeGreaterThan(size * 0.5);
    const furthest = Math.hypot(
      Math.max(
        Math.abs(minX - (size - 1) / 2),
        Math.abs(maxX - (size - 1) / 2),
      ),
      Math.max(
        Math.abs(minY - (size - 1) / 2),
        Math.abs(maxY - (size - 1) / 2),
      ),
    );
    expect(furthest).toBeLessThanOrEqual(size * 0.4);
  }
});

it("ICON-003 preserves app identity and existing browser data when icon metadata changes", () => {
  const manifest = JSON.parse(
      readFileSync("public/manifest.webmanifest", "utf8"),
    ),
    savedWine = {
      id: "savedwine",
      name: "Собер Баш",
      winery: "Винодельня Собер Баш",
      year: 2023,
      image: "",
      description: "Сохранённая запись",
    };
  expect(manifest).toMatchObject({
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    name: "Своё вино",
  });
  localStorage.setItem("wine-demo-saved-v1", JSON.stringify([savedWine]));
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Сохранённое" }));
  expect(screen.getByRole("button", { name: "Собер Баш, 2023" })).toBeVisible();
  expect(
    createHash("sha256")
      .update(readFileSync("public/assets/icon-24.png"))
      .digest("hex"),
  ).toBe("cb8fb933f6842f7c17133159acc89894e41ed3681ab4c30331fa7614933b33a6");
});

it("UI-015 browser and installed app share the selected v2 theme", () => {
  const manifest = JSON.parse(
    readFileSync("public/manifest.webmanifest", "utf8"),
  );
  const html = new DOMParser().parseFromString(
    readFileSync("index.html", "utf8"),
    "text/html",
  );
  expect(manifest.theme_color).toBe("#8f3d42");
  expect(manifest.background_color).toBe("#fefdfa");
  expect(
    html.querySelector('meta[name="theme-color"]')?.getAttribute("content"),
  ).toBe(manifest.theme_color);
});
