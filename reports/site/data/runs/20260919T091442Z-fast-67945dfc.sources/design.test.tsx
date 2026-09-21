import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from './App';

const css=readFileSync(join(process.cwd(),'src/overrides.css'),'utf8');
const base=readFileSync(join(process.cwd(),'src/styles.css'),'utf8');
afterEach(cleanup);

describe('atlas design contract',()=>{
  it('DESIGN-001 uses the atlas wine token and 82px primary action',()=>{expect(base).toContain('--wine:#742c46');expect(base).toContain('.scan-button{min-height:82px');expect(base).toContain('border-radius:18px')});
  it('DESIGN-002 renders 24px camera and 28px scan glyph rules',()=>{expect(css).toMatch(/scan-button>svg:first-child\{width:24px;height:24px/);expect(css).toMatch(/scan-button>svg:last-child\{width:28px;height:28px/);render(<App/>);const action=screen.getByRole('button',{name:/Сканировать вино/i});expect(action.querySelectorAll('svg')).toHaveLength(2)});
  it('DESIGN-003 declares the actual TrueType Onest files and every specified weight',()=>{for(const [file,weight] of [['onest-0.woff2','400'],['onest-1.woff2','500'],['onest-2.woff2','600'],['onest-3.woff2','700'],['onest-4.woff2','800']]){const font=readFileSync(join(process.cwd(),'public/assets',file));expect(font.byteLength).toBeGreaterThan(1000);expect([...font.subarray(0,4)]).toEqual([0,1,0,0]);expect(base+css).toContain(`font-weight:${weight}`)}expect(base+css).not.toContain("format('woff2')");expect(base+css).toContain("format('truetype')")});
  it('DESIGN-004 declares the 390 768 and 1280 responsive rules',()=>{expect(css).toContain('@media(max-width:390px)');expect(css).toContain('@media(min-width:768px)');expect(css).toContain('@media(min-width:1280px)');expect(css).toContain('max-width:520px')});
  it('DESIGN-005 keeps the production root free of demo controls and device chrome',()=>{render(<App/>);expect(screen.queryByLabelText(/Управление демонстрацией/i)).not.toBeInTheDocument();expect(screen.getByTestId('app')).toBeVisible();expect(document.querySelector('.phone')).not.toBeInTheDocument()});
});
