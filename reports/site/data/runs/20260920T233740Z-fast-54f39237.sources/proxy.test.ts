// @vitest-environment node
import { expect, it } from 'vitest';
import config from '../vite.config';
it('UI-025 local API proxy preserves Host for same-origin write validation',()=>{
 const proxy=(config as {server:{proxy:Record<string,unknown>}}).server.proxy;
 expect(proxy['/v1']).toMatchObject({changeOrigin:false});
});
