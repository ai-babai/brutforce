import { afterEach, describe, expect, it, vi } from 'vitest';
import { getCatalog, getRecommendations, searchWine, uploadPhoto, InvalidPhotoError } from './api';

const candidate = { id: 'cabernet', name: 'Каберне Совиньон', winery: 'Долина', year: 2023, image: '/assets/concept-bottle.png', description: 'Красное вино.' };
const catalog = { demo: true, candidates: [candidate], catalogVersion: 'demo-v2' };
const receipt = { id: '0123456789abcdef0123456789abcdef', createdAt: '2026-09-19T09:00:00Z', bytes: 5, mime: 'image/jpeg', width: 100, height: 100 };
const response = (data: unknown) => ({ ok: true, json: async () => data });

afterEach(() => vi.unstubAllGlobals());

describe('UI-025 versioned API client', () => {
  it('requests the v2 catalog, uploads a photo receipt, and searches with the receipt body', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(catalog))
      .mockResolvedValueOnce(response(receipt))
      .mockResolvedValueOnce(response({ ...catalog, selectedId: candidate.id }));
    vi.stubGlobal('fetch', fetchMock);

    await getCatalog();
    await uploadPhoto(new File(['jpeg'], 'label.jpg', { type: 'image/jpeg' }));
    await searchWine('exact', 'Каберне', undefined, receipt.id);

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v2/catalog?limit=24&cursor=&q=', { signal: undefined });
    const upload = fetchMock.mock.calls[1];
    expect(upload[0]).toBe('/v1/photos');
    expect(upload[1]).toMatchObject({ method: 'POST', signal: undefined });
    expect((upload[1] as RequestInit).body).toBeInstanceOf(FormData);
    const form = (upload[1] as RequestInit).body as FormData;
    expect(form.get('photo')).toBeInstanceOf(File);
    expect((form.get('photo') as File).name).toBe('label.jpg');
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/v1/search', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ scenario: 'exact', query: 'Каберне', photoId: receipt.id }),
      signal: undefined,
    });
  });
});

it('UI-011 distinguishes rejected image content from temporary upload failures',async()=>{
 const file=new File(['not a jpeg'],'label.jpg',{type:'image/jpeg'});
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:400,json:async()=>({error:{code:'invalid_photo',message:'internal detail'}})}));
 await expect(uploadPhoto(file)).rejects.toBeInstanceOf(InvalidPhotoError);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({error:{code:'storage_unavailable'}})}));
 await expect(uploadPhoto(file)).rejects.not.toBeInstanceOf(InvalidPhotoError);
});

it('validates recommendation responses and sends the bounded card request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(response({
    demo: false,
    candidates: [candidate],
    catalogVersion: 'catalog-1',
    modelVersion: 'roman-1',
  }));
  vi.stubGlobal('fetch', fetchMock);
  await expect(getRecommendations(candidate.id)).resolves.toMatchObject({ candidates: [candidate] });
  expect(fetchMock).toHaveBeenCalledWith('/v1/recommendations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ wineId: candidate.id, limit: 3 }),
    signal: undefined,
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ demo: false, candidates: [{ id: candidate.id }] })));
  await expect(getRecommendations(candidate.id)).rejects.toThrow(/некорректные рекомендации/i);
});

it('rejects catalog records with a non-HTTP source URL', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({
    demo: false,
    catalogVersion: 'v2',
    candidates: [{ ...candidate, sourceUrl: 'javascript:alert(1)' }],
  })));
  await expect(getCatalog()).rejects.toThrow(/некорректные данные/i);
});
