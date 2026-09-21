import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from './App';

const css=readFileSync(join(process.cwd(),'src/overrides.css'),'utf8');
const base=readFileSync(join(process.cwd(),'src/styles.css'),'utf8');
afterEach(()=>{cleanup();vi.restoreAllMocks()});

describe('atlas design contract',()=>{
  it('DESIGN-001 uses the atlas wine token and 82px primary action',()=>{expect(base).toContain('--wine:#742c46');expect(base).toContain('.scan-button{min-height:82px');expect(base).toContain('border-radius:18px')});
  it('DESIGN-002 renders 24px camera and 28px scan glyph rules',()=>{expect(css).toMatch(/scan-button>svg:first-child\{width:24px;height:24px/);expect(css).toMatch(/scan-button>svg:last-child\{width:28px;height:28px/);render(<App/>);const action=screen.getByRole('button',{name:/Сканировать вино/i});expect(action.querySelectorAll('svg')).toHaveLength(2)});
  it('DESIGN-003 declares the actual TrueType Onest files and every specified weight',()=>{for(const [file,weight] of [['onest-0.woff2','400'],['onest-1.woff2','500'],['onest-2.woff2','600'],['onest-3.woff2','700'],['onest-4.woff2','800']]){const font=readFileSync(join(process.cwd(),'public/assets',file));expect(font.byteLength).toBeGreaterThan(1000);expect([...font.subarray(0,4)]).toEqual([0,1,0,0]);expect(base+css).toContain(`font-weight:${weight}`)}expect(base+css).not.toContain("format('woff2')");expect(base+css).toContain("format('truetype')")});
  it('DESIGN-004 separates the 390px page padding from the 360px button geometry',()=>{expect(css).toContain('@media(max-width:390px)');expect(css).toContain('#UI-001 .hero{margin-left:-18px;margin-right:-18px}');expect(css).toContain('@media(max-width:360px)');expect(css).toMatch(/@media\(max-width:360px\).*grid-template-columns:36px minmax\(0,1fr\) 28px/);expect(css).toContain('padding:15px 12px');expect(css).toContain('#UI-001 .hero{flex-shrink:0}');expect(css).toContain('@media(max-height:600px){#UI-001 .hero{height:auto;min-height:210px}')});
  it('DESIGN-005 keeps the application free of demo controls',()=>{render(<App/>);expect(screen.queryByLabelText(/Управление демонстрацией/i)).not.toBeInTheDocument();expect(screen.getByTestId('app')).toBeVisible();expect(document.querySelector('.phone')).not.toBeInTheDocument()});
  it('DESIGN-006 applies atlas typography to welcome candidates result and errors',()=>{expect(css).toContain('#UI-001 .hero h1{font-size:30px;line-height:1.12;letter-spacing:-1.35px}');expect(css).toContain('#UI-006 h2{font-size:26px');expect(css).toContain('#UI-007 .result-hero h2{font-size:26px');expect(css).toContain('#UI-010 h2,#UI-011 h2{font-size:29px')});
  it('DESIGN-007 preserves 48px actions and exact camera shutter geometry',()=>{expect(css).toContain('.shutter{width:66px;height:66px;border-width:2px;padding:4px}');expect(css).toContain('.top button,.tabs button,.text-button{min-width:48px;min-height:48px}')});
  it('DESIGN-008 renders the camera surface as a dark live-video container',()=>{expect(css).toContain('background:#211d23;color:white');expect(css).toContain('.viewfinder video{width:100%;height:100%;min-height:0;object-fit:cover}')});
  it('DESIGN-009 keeps candidate rows fully actionable with explicit metadata type',()=>{expect(css).toContain('.candidate-list b{font-size:14px;line-height:1.25;font-weight:600}');expect(css).toContain('.candidate-list small{font-size:11px}')});
  it('DESIGN-010 bounds camera to the dynamic viewport with a shrinkable preview',()=>{expect(css).toContain('height:100dvh;min-height:0!important;max-height:100dvh;overflow:hidden');expect(css).toContain('grid-template-rows:auto minmax(0,1fr) auto');expect(css).not.toContain('.viewfinder video{width:100%;height:100%;min-height:320px')});
  it('DESIGN-011 keeps camera actions in flow with safe-area and short-landscape rules',()=>{expect(css).toContain('.camera-actions{display:grid;grid-template-columns:1fr 66px 1fr');expect(css).toContain('env(safe-area-inset-bottom)');expect(css).toContain('@media(max-height:500px) and (orientation:landscape)');expect(css).toContain('.camera-actions{grid-template-columns:1fr;grid-template-rows:1fr 66px 1fr')});
});

it('DESIGN-012 keeps the hint outside the framed camera image',()=>{
 const old=navigator.mediaDevices;
 Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:vi.fn(()=>new Promise(()=>{}))}});
 try {render(<App/>);fireEvent.click(screen.getByRole('button',{name:/Сканировать вино/}));
 const hint=screen.getByText('Нужная бутылка по центру');
 expect(hint.closest('.viewfinder')).toBeNull();
 expect(hint.parentElement).toHaveClass('camera-preview');
 expect(document.querySelector('.camera-preview>.viewfinder .camera-frame')).not.toBeNull();
 expect(css).toContain('.camera-preview{display:grid;grid-template-rows:minmax(0,1fr) auto;min-height:0');
 expect(css).toContain('.camera-preview>.neighbor-hint{position:static');
 } finally {Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:old})}
});

it('DESIGN-013 matches the approved Atlas scanner and target vector geometry',()=>{
 const source=readFileSync(join(process.cwd(),'../../design/wine-ux-atlas/site/assets/icons.js'),'utf8');
 const icons=JSON.parse(source.slice(source.indexOf('{')).trim().replace(/;$/,''));
 render(<App/>);
 for(const name of ['scan','focus-2']){
  const svg=document.querySelector(`[data-atlas-icon="${name}"]`)!;
  expect(svg).not.toBeNull();expect(svg.getAttribute('viewBox')).toBe('0 0 24 24');
  const expected=new DOMParser().parseFromString(icons[name],'image/svg+xml');
  expect(Array.from(svg.querySelectorAll('path'),p=>[p.getAttribute('d'),p.getAttribute('fill')])).toEqual(Array.from(expected.querySelectorAll('path'),p=>[p.getAttribute('d'),p.getAttribute('fill')]));
 }
});
it('DESIGN-014 restores the complete airy welcome guidance from Atlas',()=>{
 render(<App/>);const tip=document.querySelector('#UI-001 .tip')!;
 expect(tip.querySelector('.tip-icon [data-atlas-icon="focus-2"]')).not.toBeNull();
 expect(tip.querySelector('strong')).toHaveTextContent('Нужная бутылка по центру');
 expect(tip.querySelector('p')).toHaveTextContent('Поверните этикетку к камере.Соседние бутылки могут быть в кадре.');
 expect(tip.querySelector('p br')).not.toBeNull();
 expect(css).toContain('background:transparent;padding:0;border-radius:0;margin:27px 0 21px');
 expect(css).toContain('flex:0 0 34px;width:34px;height:34px');
 expect(css).toContain('font-size:10px;margin:3px 0 0;line-height:1.5');expect(css).toContain('font-size:11px;font-weight:500;line-height:1.5');
});

it('DESIGN-015 limits the decorative phone frame to wide screens',()=>{
 const desktop=css.slice(css.indexOf('@media(min-width:1024px)'));
 expect(desktop).toContain('border:10px solid #29262b;border-radius:46px');
 expect(desktop).toContain('place-items:center');
 expect(desktop).toContain('width:410px');
 expect(css.slice(0,css.indexOf('@media(min-width:1024px)'))).not.toContain('border:10px solid #29262b');
 render(<App/>);expect(screen.getByRole('button',{name:/Сканировать вино/})).toBeVisible();
 expect(screen.getByTestId('app').parentElement).toHaveClass('app-shell');
});
it('DESIGN-016 camera uses the available desktop phone height, not the outer viewport',()=>{
 const desktop=css.slice(css.indexOf('@media(min-width:1024px)'));
 expect(desktop).toContain('--device-screen-height:min(820px,calc(100dvh - 100px))');
 expect(desktop).toContain('.camera-page{width:100%;max-width:none;height:var(--device-screen-height);max-height:var(--device-screen-height)');
 expect(desktop).toContain('grid-template-rows:auto minmax(0,1fr) auto');
 expect(desktop).toContain('overflow:hidden');
 expect(css).toContain('.app-content{min-height:0;overflow-y:auto');
});
it('DESIGN-017 keeps the three equal Tabler navigation actions outside the scroll region',()=>{
 render(<App/>);const nav=screen.getByRole('navigation',{name:'Основная навигация'});
 expect(nav.parentElement).toBe(screen.getByTestId('app'));expect(nav.previousElementSibling).toHaveClass('app-content');
 expect(nav.querySelectorAll(':scope > button')).toHaveLength(3);expect(nav.querySelectorAll('.tabler-icon')).toHaveLength(3);
 expect(css).toContain('.bottom-nav{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))');
 expect(css).toContain('env(safe-area-inset-bottom)');expect(css).toContain('.app-content{min-height:0;overflow-y:auto');
});
it('DESIGN-018 marks only the current product section and uses the Atlas footer treatment',()=>{
 render(<App/>);expect(screen.getByRole('button',{name:'Сканер'})).toHaveAttribute('aria-current','page');
 expect(screen.getAllByText('Информация о российских винах')[0]).toBeVisible();
 expect(css).toContain('.product-footer{margin-top:auto;padding:28px 0 0;color:#766772;text-align:center;font-size:11px}');
 expect(css).toContain('.bottom-nav button[aria-current="page"]{color:var(--wine)}');
});
it('DESIGN-019 keeps result save in a compact, stable header target',()=>{
 render(<App/>);
 expect(css).toContain('.top-with-action{grid-template-columns:48px minmax(0,1fr) 92px}');
 expect(css).toContain('.top .save-header-action{display:flex;width:92px;height:48px;min-width:92px;min-height:48px');
 expect(css).toContain('border:0;border-radius:0;background:transparent;color:var(--wine);font-size:11px');
 expect(css).toContain('.top-with-action>b{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}');
});
it('DESIGN-020 groups search input and submit into one focused control',()=>{
 render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Поиск'}));
 const input=screen.getByLabelText(/Название вина/i);const field=input.parentElement!;const submit=screen.getByRole('button',{name:'Искать'});
 expect(field).toHaveClass('search-field');expect(field).toContainElement(input);expect(field).toContainElement(submit);
 expect(css).toContain('.search-field{display:grid;grid-template-columns:minmax(0,1fr) 52px;min-width:0;overflow:hidden;border:1px solid #cbbbc4;border-radius:14px;background:#fff}');
 expect(css).toContain('.search-field:focus-within{border-color:#b66f8e;box-shadow:0 0 0 2px #b66f8e}');
 expect(css).toContain('.search-field input{min-width:0;height:52px;border:0;border-radius:0;outline:0}');
 expect(css).toContain('.search-field button{display:grid;min-width:48px;min-height:48px;place-items:center;border:0;border-radius:0;background:var(--wine);color:#fff}');
 expect(css).toContain('.search-field button:focus-visible{outline:0;box-shadow:inset 0 0 0 3px #f3cbdc}');
 expect(css).toContain('#UI-008 form{margin:18px 0 16px}');
});
