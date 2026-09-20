import { readFileSync } from 'node:fs';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from './App';
import { InstallApp } from './InstallApp';
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
const mode=(standalone:boolean)=>vi.stubGlobal('matchMedia',()=>({matches:standalone}));
function offer(outcome='dismissed',reject=false){const prompt=reject?vi.fn().mockRejectedValue(new Error('unavailable')):vi.fn().mockResolvedValue(undefined);const event=Object.assign(new Event('beforeinstallprompt',{cancelable:true}),{prompt,userChoice:Promise.resolve({outcome})});act(()=>{window.dispatchEvent(event)});return prompt}
it('UI-012 ordinary browser remains usable without installation support',()=>{mode(false);render(<App/>);expect(screen.getByRole('button',{name:/Сканировать вино/})).toBeVisible();expect(screen.queryByRole('button',{name:'Установить приложение'})).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'По названию'}));expect(screen.getByLabelText(/Название вина/)).toBeVisible()});
it('UI-013 installation only opens on click; dismissal preserves the web journey',async()=>{mode(false);render(<App/>);const prompt=offer();expect(prompt).not.toHaveBeenCalled();await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Установить приложение'}))});expect(prompt).toHaveBeenCalledOnce();expect(screen.getByRole('button',{name:/Сканировать вино/})).toBeVisible();expect(screen.queryByRole('button',{name:'Установить приложение'})).not.toBeInTheDocument()});
it('UI-013 refused browser install prompt does not break the page',async()=>{mode(false);render(<InstallApp/>);offer('dismissed',true);await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Установить приложение'}))});expect(screen.queryByRole('button')).not.toBeInTheDocument()});
it('UI-014 standalone exposes the same application without an install offer',()=>{mode(true);render(<App/>);offer();expect(screen.queryByRole('button',{name:'Установить приложение'})).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'По названию'}));expect(screen.getByLabelText(/Название вина/)).toBeVisible()});
it('UI-014 successful installation removes the offer',()=>{mode(false);render(<InstallApp/>);offer();act(()=>{window.dispatchEvent(new Event('appinstalled'))});expect(screen.queryByRole('button')).not.toBeInTheDocument()});
it('UI-015 install manifest launches the same root with real PNG icons',()=>{const manifest=JSON.parse(readFileSync('public/manifest.webmanifest','utf8'));expect(manifest).toMatchObject({start_url:'/',scope:'/',display:'standalone'});expect(manifest.icons.map((i:{sizes:string})=>i.sizes)).toEqual(['192x192','512x512']);for(const icon of manifest.icons){const bytes=readFileSync('public'+icon.src);expect(bytes.subarray(1,4).toString()).toBe('PNG');const size=Number(icon.sizes.split('x')[0]);expect(bytes.readUInt32BE(16)).toBe(size);expect(bytes.readUInt32BE(20)).toBe(size)}expect(readFileSync('index.html','utf8')).toContain('rel="manifest"');expect(readFileSync('index.html','utf8')).toContain('viewport-fit=cover')});

it('UI-015 browser and installed app share the selected v2 theme',()=>{
 const manifest=JSON.parse(readFileSync('public/manifest.webmanifest','utf8'));
 const html=new DOMParser().parseFromString(readFileSync('index.html','utf8'),'text/html');
 expect(manifest.theme_color).toBe('#8f3d42');
 expect(manifest.background_color).toBe('#fefdfa');
 expect(html.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe(manifest.theme_color);
});
