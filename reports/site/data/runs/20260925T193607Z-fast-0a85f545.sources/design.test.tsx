import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';
import { MascotScene, V2Logo } from './V2Visual';

const css = readFileSync(join(process.cwd(), 'src/v2.css'), 'utf8');
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('selected Wine UX 2.0 design contract', () => {
  it('DESIGN-001 uses the selected wine and warm-surface tokens', () => {
    expect(css).toContain('--wine:#8f3d42');
    expect(css).toContain('--paper:#fefdfa');
    expect(css).toContain('--cream:#fdf9ed');
  });

  it('DESIGN-003 keeps locally hosted Onest and selected Playfair display type', () => {
    for (const asset of ['onest-0.woff2', 'onest-1.woff2', 'onest-2.woff2', 'onest-3.woff2']) expect(readFileSync(join(process.cwd(), 'public/assets', asset)).byteLength).toBeGreaterThan(1_000);
    expect(readFileSync(join(process.cwd(), 'public/assets/v2/PlayfairDisplay-VariableFont_wght.woff2')).byteLength).toBeGreaterThan(10_000);
    expect(css).toContain('font-family:"Playfair Display V2"');
    expect(css).toContain('#UI-001 .hero h1{width:100%;margin:0 0 14px;font-family:var(--serif)');
  });

  it('DESIGN-022 joins the welcome header and hero on one warm surface', () => {
    render(<App />);
    expect(document.querySelector('#UI-001 .brand.v2-brand')?.parentElement).toHaveClass('welcome-intro');
    expect(css).toContain('#UI-001 .welcome-intro{margin:-18px -22px 0;padding:18px 22px 0;background:#fbf6ec}');
    expect(css).toContain('.brand.v2-brand{min-height:56px;margin-top:12px;padding:10px 12px;border-radius:0;background:transparent;backdrop-filter:none;-webkit-backdrop-filter:none}');
    expect(css).toContain('@media(max-width:390px){#UI-001 .welcome-intro{margin-right:-18px;margin-left:-18px;padding-right:18px;padding-left:18px}');
    expect(css).toContain('@media(min-width:768px){#UI-001 .welcome-intro{margin-top:-28px;padding-top:28px}}');
    expect(css).toContain('@media(min-width:1024px){#UI-001 .welcome-intro{margin-top:-24px;padding-top:24px}}');
  });

  it('DESIGN-004 keeps 320px actions reachable with a reduced centered mascot panel', () => {
    expect(css).toContain('@media(max-width:360px)');
    expect(css).toContain('#UI-001 .hero>.mascot-scene{height:160px}');
    expect(css).toContain('.scan-button>span{display:grid;min-width:0;overflow-wrap:anywhere;gap:4px}');
    expect(css).toContain('white-space:normal;overflow-wrap:anywhere;min-width:0');
    expect(css).toContain('#UI-001 .hero>.mascot-scene{width:100%;height:220px');
    expect(css).toContain('.scan-button{grid-template-columns:36px minmax(0,1fr) 24px');
  });

  it('DESIGN-002 keeps the primary scanner action whole, labeled, and touch-safe', () => {
    render(<App />);
    const action = screen.getByRole('button', { name: /Сканировать вино/i });
    expect(action.querySelectorAll('svg')).toHaveLength(2);
    expect(action.querySelector('small')).toBeNull();
    expect(css).toContain('.scan-button{min-height:78px;display:grid;grid-template-columns:39px minmax(0,1fr) 24px');
    expect(css).toContain('.scan-button>svg:first-child{width:20px;height:20px;padding:9px');
  });

  it('DESIGN-005 renders only the product application, without report controls or prototype chrome', () => {
    render(<App />);
    expect(screen.getByTestId('app')).toBeVisible();
    expect(document.querySelector('.phone,.demo-shell,.demo-controls,.demo-banner')).toBeNull();
    expect(screen.queryByLabelText(/Управление демонстрацией/i)).not.toBeInTheDocument();
  });

  it('DESIGN-006 applies the selected centered display hierarchy to the welcome heading', () => {
    expect(css).toContain('#UI-001 .hero h1{width:100%;margin:0 0 14px;font-family:var(--serif);font-size:36px;font-weight:650;line-height:1.08;letter-spacing:-1px;text-align:center;text-wrap:balance}');
    expect(css).toContain('.page h2{font-family:var(--serif);font-weight:650');
    render(<App />);
    const heading = screen.getByRole('heading', { name: /Какое вино/i });
    expect(heading).toBeVisible();
    expect(heading.querySelector('br')).toBeNull();
  });

  it('DESIGN-008 uses a dark real-video camera surface', () => {
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn(() => new Promise(() => {})) } });
    try {
      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: /Сканировать вино/i }));
      expect(screen.getByLabelText('Изображение с камеры').tagName).toBe('VIDEO');
      expect(css).toContain('.camera-page{height:100dvh;min-height:0!important;max-height:100dvh');
      expect(css).toContain('background:#211d23;color:#fff');
      expect(css).toContain('.viewfinder video{width:100%;height:100%;min-height:0;object-fit:cover}');
    } finally { Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: mediaDevices }); }
  });

  it('DESIGN-009 keeps candidate rows as full actionable surfaces with readable metadata', () => {
    expect(css).toContain('.leader-list button{grid-template-columns:56px minmax(0,1fr)');
    expect(css).toContain('.leader-list b{overflow-wrap:anywhere;font-size:14px');
    expect(css).toContain('.leader-list small{overflow-wrap:anywhere;white-space:normal');
  });

  it('SR-009 constrains the leader badge and preserves full titles at enlarged text', () => {
    expect(css).toContain('.leader-list button.candidate-leader{grid-template-columns:76px minmax(0,1fr)');
    expect(css).toContain('.leader-list .candidate-leader img,.leader-list .candidate-leader .missing-image{width:76px;height:132px');
    expect(css).toContain('.leader-list img,.leader-list .missing-image{width:56px;height:98px');
    expect(css).toContain('max-inline-size:100%');
    expect(css).toContain('overflow-wrap:anywhere');
  });

  it('DESIGN-007 and DESIGN-010 preserve the real camera shutter and dynamic viewport', () => {
    expect(css).toContain('.camera-page{height:100dvh;min-height:0!important;max-height:100dvh');
    expect(css).toContain('grid-template-rows:auto minmax(0,1fr) auto');
    expect(css).toContain('.shutter{width:66px;height:66px;margin:0;border:2px solid #fff');
  });

  it('DESIGN-011 keeps camera controls in flow with safe-area and landscape rules', () => {
    expect(css).toContain('.camera-actions{display:grid;grid-template-columns:1fr 66px 1fr');
    expect(css).toContain('env(safe-area-inset-bottom)');
    expect(css).toContain('@media(max-height:500px) and (orientation:landscape)');
    expect(css).toContain('.camera-actions{grid-template-columns:1fr;grid-template-rows:1fr 66px 1fr');
  });

  it('DESIGN-012 keeps the camera guidance outside the framed video', () => {
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn(() => new Promise(() => {})) } });
    try {
      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: /Сканировать вино/i }));
      const hint = screen.getByText('Нужная бутылка по центру');
      expect(hint.closest('.viewfinder')).toBeNull();
      expect(hint.parentElement).toHaveClass('camera-preview');
      expect(document.querySelector('.camera-preview>.viewfinder .camera-frame')).not.toBeNull();
      expect(css).toContain('.camera-preview{display:grid;grid-template-rows:minmax(0,1fr) auto;min-height:0');
      expect(css).toContain('.camera-preview>.neighbor-hint{display:block');
    } finally { Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: mediaDevices }); }
  });

  it('DESIGN-013 preserves the approved Atlas scan vector on the camera CTA', () => {
    const source = readFileSync(join(process.cwd(), '../../design/wine-ux-atlas/site/assets/icons.js'), 'utf8');
    const icons = JSON.parse(source.slice(source.indexOf('{')).trim().replace(/;$/, ''));
    render(<App />);
    for (const name of ['scan']) {
      const svg = document.querySelector(`[data-atlas-icon="${name}"]`)!;
      const expected = new DOMParser().parseFromString(icons[name], 'image/svg+xml');
      expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
      expect(Array.from(svg.querySelectorAll('path'), path => [path.getAttribute('d'), path.getAttribute('fill')])).toEqual(Array.from(expected.querySelectorAll('path'), path => [path.getAttribute('d'), path.getAttribute('fill')]));
    }
  });

  it('DESIGN-014 renders the accepted centered one-line guidance card', () => {
    render(<App />);
    const tip = document.querySelector('#UI-001 .tip')!;
    expect(tip).toHaveClass('welcome-tip');
    expect(tip).toHaveTextContent('Этикетка целиком, нужная бутылка по центру.');
    expect(tip.querySelector('.tip-icon')).toBeNull();
    expect(css).toContain('#UI-001 .welcome-tip{display:block;margin-top:14px;margin-bottom:15px;padding:12px 14px;border:1px solid #eadfd4;border-radius:14px;background:#fcf7ef;text-align:center;text-wrap:balance}');
  });

  it('DESIGN-015 and DESIGN-017 preserve the desktop frame and app navigation shell', () => {
    expect(css).toContain('@media(min-width:1024px){.app-shell{--device-screen-height:min(820px,calc(100dvh - 100px))');
    expect(css).toContain('border:10px solid #29262b;border-radius:46px');
    render(<App />);
    const nav = screen.getByRole('navigation', { name: 'Основная навигация' });
    expect(nav.parentElement).toBe(screen.getByTestId('app'));
    expect(nav.previousElementSibling).toHaveClass('app-content');
    expect(nav.querySelectorAll(':scope > button')).toHaveLength(3);
  });

  it('DESIGN-016 makes the camera use the desktop phone interior, not the outer viewport', () => {
    expect(css).toContain('--device-screen-height:min(820px,calc(100dvh - 100px))');
    expect(css).toContain('.app-shell>.app .camera-page{width:100%;max-width:none;height:var(--device-screen-height);max-height:var(--device-screen-height)');
    expect(css).toContain('grid-template-rows:auto minmax(0,1fr) auto');
    expect(css).toContain('.app-content{min-height:0;overflow-y:auto');
  });

  it('DESIGN-018 marks the active product section and retains the product footer', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: 'Главная' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('Информация о российских винах')).toBeVisible();
    expect(css).toContain('.bottom-nav{gap:4px;padding:8px 12px max(10px,env(safe-area-inset-bottom));border-top-color:#e9dfd3;background:#fefdfa}');
    expect(css).toContain('.bottom-nav button{min-height:48px;gap:4px;border-radius:12px;color:#746e68;font:500 11px/1.2 Onest,sans-serif}');
    expect(css).toContain('.bottom-nav button[aria-current="page"]{background:#f5e8df;color:#8f3d42}');
    expect(css).toContain('.product-footer{margin-top:auto;padding:28px 0 0;color:#766772;text-align:center;font-size:11px}');
  });

  it('DESIGN-019 and DESIGN-020 keep compact save and a single search control', () => {
    expect(css).toContain('.top-with-action{grid-template-columns:48px minmax(0,1fr) 92px}');
    expect(css).toContain('.top .save-header-action{display:flex;width:92px;height:48px;min-width:92px');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Поиск' }));
    const input = screen.getByLabelText(/Название вина/i);
    expect(input.parentElement).toHaveClass('search-field');
    expect(input.parentElement).toContainElement(screen.getByRole('button', { name: 'Искать' }));
  });

  it('DESIGN-022 places selected mascots only in their approved rendered app states', () => {
    const mediaDevices = navigator.mediaDevices;
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn(() => new Promise(() => {})) } });
    render(<App />);
    expect(screen.getByAltText('Своё Вино')).toHaveAttribute('src', '/assets/v2/svoe-vino-logo.svg');
    expect(screen.getByAltText('Пёс-детектив держит бутылку, этикетка обращена к вам')).toHaveAttribute('src', '/assets/v2/mascot-hold-2d-alpha.webp');
    expect(screen.queryByText('Поиск по этикетке')).not.toBeInTheDocument();
    const homeArt = readFileSync(join(process.cwd(), 'public/assets/v2/mascot-hold-2d-alpha.webp'));
    expect(homeArt.toString('ascii', 12, 16)).toBe('VP8X');
    expect(homeArt[20] & 0x10).toBe(0x10); // WebP extended-format alpha flag.
    expect(css).toContain('mix-blend-mode:normal');
    fireEvent.click(screen.getByRole('button', { name: /Сканировать вино/i }));
    expect(document.querySelector('#UI-002 .mascot-scene')).toBeNull();
    cleanup();
    render(<App simulatePermissionDenied />);
    fireEvent.click(screen.getByRole('button', { name: /Сканировать вино/i }));
    expect(document.querySelector('#UI-003 .mascot-scene')).toBeNull();
    cleanup();
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Поиск' }));
    expect(document.querySelector('#UI-008 .mascot-scene-browse')).not.toBeNull();
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: mediaDevices });
    cleanup();
    render(<><V2Logo /><MascotScene scene="walk" /><MascotScene scene="counter" /><MascotScene scene="browse" /><MascotScene scene="offline" /></>);
    expect(document.querySelectorAll('.mascot-scene[aria-hidden="true"]')).toHaveLength(4);
    for (const asset of ['mascot-hold-2d-alpha.webp', 'mascot-walk-2d-alpha.webp', 'mascot-counter-thoughtful-2d-alpha.webp', 'mascot-cellar-2d-alpha.webp', 'mascot-offline-2d-alpha.webp']) {
      const bytes = readFileSync(join(process.cwd(), 'public/assets/v2', asset));
      expect(bytes.byteLength).toBeGreaterThan(50_000);
      expect(bytes.toString('ascii', 12, 16)).toBe('VP8X');
      expect(bytes[20] & 0x10).toBe(0x10);
    }
    for (const image of document.querySelectorAll('.mascot-scene img')) expect(image.getAttribute('src')).toMatch(/-alpha\.webp$/);
    expect(css).not.toMatch(/mix-blend-mode:\s*multiply/);
    expect(css).not.toMatch(/(?:-webkit-)?mask-image:/);
    expect(css).toContain('#UI-001 .hero{display:flex;flex-direction:column;align-items:center;min-height:0;margin:0;background:#fbf6ec;overflow:visible;text-align:center}');
    expect(css).toContain('#UI-001 .hero>.mascot-scene{position:relative;right:auto;bottom:auto;width:100%;height:260px;margin:6px 0 0;background:transparent;mix-blend-mode:normal}');
    expect(css).not.toContain('concept-bottle.png');
  });

  it('DESIGN-022 gives photo no-match actions the approved full-width geometry', () => {
    expect(css).toContain('#UI-009 .missing-actions{display:grid;gap:10px}');
    expect(css).toContain('#UI-009 .missing-actions .primary,#UI-009 .missing-actions .secondary{min-height:56px;border-radius:16px;text-align:center}');
  });
});
