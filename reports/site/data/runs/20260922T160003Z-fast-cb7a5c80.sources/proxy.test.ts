// @vitest-environment node
import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
import config from '../vite.config';

it('UI-025 local API proxy preserves Host and proxies catalog assets',()=>{
 const proxy=(config as {server:{proxy:Record<string,unknown>}}).server.proxy;
 expect(proxy['/v1']).toMatchObject({changeOrigin:false});
 const source=readFileSync(new URL('../vite.config.ts',import.meta.url),'utf8');
 expect(source).toMatch(/'\/v2': \{ target: 'http:\/\/localhost:8097', changeOrigin: false \}/);
 expect(source).toMatch(/'\/catalog-assets': \{ target: 'http:\/\/localhost:8097', changeOrigin: false \}/);
});
