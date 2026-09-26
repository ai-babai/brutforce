import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const receipt = {
  id: '0123456789abcdef0123456789abcdef',
  createdAt: '2026-09-25T09:00:00Z',
  bytes: 5,
  mime: 'image/jpeg',
  width: 100,
  height: 100,
};
const candidate = {
  id: 'wine-a',
  name: 'Резерв',
  winery: 'Винодельня А',
  year: 2023,
  image: '',
  description: 'Описание из каталога',
};
const response = (data: unknown) => ({ ok: true, status: 200, json: async () => data });
const upload = () => userEvent.upload(
  screen.getByLabelText(/Загрузить фотографию/i),
  new File(['image'], 'label.jpg', { type: 'image/jpeg' }),
);

beforeEach(() => {
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:air35-photo'),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Air 3.5 product UI', () => {
  it('keeps one home action group without the duplicate framing hint', () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: 'Какое вино перед вами?' })).toBeVisible();
    expect(document.querySelector('#UI-001 .mascot-scene-home')).not.toBeNull();
    expect(screen.getByRole('button', { name: /Сканировать вино/i })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Выбрать фото' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'По названию' })).toBeVisible();
    expect(screen.queryByText(/Этикетка целиком, нужная бутылка по центру/i)).not.toBeInTheDocument();
    expect(document.querySelectorAll('#UI-001 .actions')).toHaveLength(1);
  });

  it('exposes the camera scene, actions and camera-only guidance', async () => {
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn(() => new Promise(() => {})) },
    });
    try {
      render(<App />);
      await userEvent.click(screen.getByRole('button', { name: /Сканировать вино/i }));

      expect(screen.getByTestId('app')).toHaveClass('camera-open');
      expect(document.querySelector('#UI-002 .camera-preview > .viewfinder video')).toBe(
        screen.getByLabelText('Изображение с камеры'),
      );
      expect(document.querySelector('#UI-002 .camera-frame')).not.toBeNull();
      expect(screen.getByText('Нужная бутылка по центру')).toBeVisible();
      expect(screen.getAllByText('Нужная бутылка по центру')).toHaveLength(1);
      expect(screen.getByText('Этикетка вина')).toBeVisible();
      expect(screen.queryByText('Наведите на этикетку')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Сделать снимок' })).toBeVisible();
      expect(screen.getByRole('button', { name: 'Выбрать из галереи' })).toBeVisible();
      expect([...document.querySelectorAll('#UI-002 .camera-actions > *')].map((item) => item.getAttribute('aria-label'))).toEqual([
        'Выбрать из галереи', 'Сделать снимок', null,
      ]);
      expect(screen.getByRole('button', { name: 'Назад' })).toBeVisible();
      expect(screen.getByRole('navigation', { name: 'Основная навигация' })).toBeVisible();
    } finally {
      Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: mediaDevices });
    }
  });

  it('keeps API order and gives only the first photo result the leader hook', async () => {
    const second = { ...candidate, id: 'wine-b', name: 'Другой резерв', year: 2021 };
    vi.stubGlobal('fetch', vi.fn((url) => Promise.resolve(response(
      url === '/v1/photos' ? receipt : { demo: false, candidates: [candidate, second] },
    ))));
    render(<App />);
    await upload();

    const first = await screen.findByRole('button', { name: /Резерв, 2023/i });
    const alternative = screen.getByRole('button', { name: /Другой резерв, 2021/i });
    expect(first).toHaveClass('candidate-leader');
    expect(alternative).not.toHaveClass('candidate-leader');
    expect([...document.querySelectorAll('#UI-006 .candidate-list > button')]).toEqual([
      first,
      alternative,
    ]);
  });

  it('uses one nav background hook and keeps it aligned with the active section', async () => {
    render(<App />);
    const nav = screen.getByRole('navigation', { name: 'Основная навигация' });
    expect(nav.querySelectorAll('.nav-slider')).toHaveLength(1);
    expect(nav).toHaveAttribute('data-section', 'scanner');

    await userEvent.click(screen.getByRole('button', { name: 'Поиск' }));
    expect(nav).toHaveAttribute('data-section', 'search');
    expect(screen.getByRole('button', { name: 'Поиск' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { name: 'Найдём по названию' })).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: 'Сохранённое' }));
    expect(nav).toHaveAttribute('data-section', 'saved');
    expect(screen.getByRole('button', { name: 'Сохранённое' })).toHaveAttribute('aria-current', 'page');

    await userEvent.click(screen.getByRole('button', { name: 'Главная' }));
    expect(nav).toHaveAttribute('data-section', 'scanner');
    expect(screen.getByRole('button', { name: 'Главная' })).toHaveAttribute('aria-current', 'page');
  });

  it.each([
    {
      action: 'no_match',
      heading: 'Ничего не найдено',
      copy: 'Сервис не нашёл подходящего совпадения.',
    },
    {
      action: 'outside_display_catalog',
      heading: 'Карточка пока недоступна',
      copy: 'Вино распознано, но его карточки пока нет в нашем каталоге.',
    },
  ])('distinguishes a real $action response', async ({ action, heading, copy }) => {
    vi.stubGlobal('fetch', vi.fn((url) => Promise.resolve(response(
      url === '/v1/photos'
        ? receipt
        : { demo: false, candidates: [], action, ...(action === 'outside_display_catalog' ? { recognizedSlug: 'organizer-only' } : {}) },
    ))));
    render(<App />);
    await upload();

    expect(await screen.findByRole('heading', { name: heading })).toBeVisible();
    expect(screen.getByText(copy)).toBeVisible();
  });
});
