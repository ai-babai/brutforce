// @vitest-environment node
import { expect, it } from 'vitest';
import config from '../vite.config.ts';

it('UI-025 local API proxy preserves Host and proxies catalog assets',()=>{
 const proxy=(config as {server:{proxy:Record<string,unknown>}}).server.proxy;
 expect(proxy['/v1']).toMatchObject({changeOrigin:false});
 expect(proxy['/v2']).toMatchObject({target:'http://localhost:8097',changeOrigin:false});
 expect(proxy['/media/catalog']).toMatchObject({target:process.env.CATALOG_MEDIA_ORIGIN || 'https://test.ops.dzap.pw',changeOrigin:true});
});
