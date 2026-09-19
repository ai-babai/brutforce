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
  it('DESIGN-004 separates the 390px page padding from the 360px button geometry',()=>{expect(css).toContain('@media(max-width:390px)');expect(css).toContain('#UI-001 .hero{margin-left:-18px;margin-right:-18px}');expect(css).toContain('@media(max-width:360px)');expect(css).toMatch(/@media\(max-width:360px\).*grid-template-columns:36px minmax\(0,1fr\) 28px/);expect(css).toContain('padding:15px 12px')});
  it('DESIGN-005 keeps the production root free of demo controls and device chrome',()=>{render(<App/>);expect(screen.queryByLabelText(/Управление демонстрацией/i)).not.toBeInTheDocument();expect(screen.getByTestId('app')).toBeVisible();expect(document.querySelector('.phone')).not.toBeInTheDocument()});
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
