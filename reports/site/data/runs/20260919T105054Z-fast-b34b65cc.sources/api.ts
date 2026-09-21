import type { PhotoReceipt, Scenario, SearchResponse } from './types';

export async function searchWine(scenario: Scenario, query?: string, signal?: AbortSignal, photoId?: string): Promise<SearchResponse> {
  const response = await fetch('/api/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario, ...(query ? { query } : {}), ...(photoId ? { photoId } : {}) }), signal });
  if (!response.ok) throw new Error('Поиск временно недоступен');
  const data: unknown = await response.json();
  if (!isSearchResponse(data)) throw new Error('Сервис вернул некорректный ответ');
  return data;
}

export async function uploadPhoto(file: File, signal?: AbortSignal): Promise<PhotoReceipt> {
  const form = new FormData(); form.append('photo',file);
  const response=await fetch('/api/photos',{method:'POST',body:form,signal});
  if(!response.ok)throw new Error('Не удалось загрузить фотографию');
  const value:unknown=await response.json();
  if(!isPhotoReceipt(value))throw new Error('Сервис вернул некорректную квитанцию');
  return value;
}

export async function getCatalog(signal?: AbortSignal):Promise<SearchResponse>{
  const response=await fetch('/api/catalog',{signal});
  if(!response.ok)throw new Error('Каталог временно недоступен');
  const data:unknown=await response.json();
  if(!isSearchResponse(data)||new Set(data.candidates.map(item=>item.id)).size!==data.candidates.length)throw new Error('Каталог вернул некорректные данные');
  return data;
}

function isPhotoReceipt(value:unknown):value is PhotoReceipt{
  if(!value||typeof value!=='object')return false; const v=value as Record<string,unknown>;
  return typeof v.id==='string'&&/^[a-f0-9]{32}$/.test(v.id)&&typeof v.createdAt==='string'&&typeof v.mime==='string'&&['bytes','width','height'].every(k=>typeof v[k]==='number'&&Number.isInteger(v[k])&&(v[k] as number)>0);
}

function isSearchResponse(value: unknown): value is SearchResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (data.demo !== true || !Array.isArray(data.candidates)) return false;
  const validCandidates = data.candidates.every(candidate => {
    if (!candidate || typeof candidate !== 'object') return false;
    const item = candidate as Record<string, unknown>;
    return ['id','name','winery','image','description'].every(key => typeof item[key] === 'string')
      && typeof item.year === 'number' && Number.isInteger(item.year);
  });
  if (!validCandidates) return false;
  if (data.selectedId === undefined) return true;
  return typeof data.selectedId === 'string' && data.candidates.some(candidate => candidate.id === data.selectedId);
}
