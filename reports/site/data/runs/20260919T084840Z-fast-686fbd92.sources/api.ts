import type { Scenario, SearchResponse } from './types';

export async function searchWine(scenario: Scenario, query?: string, signal?: AbortSignal): Promise<SearchResponse> {
  const response = await fetch('/api/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario, ...(query ? { query } : {}) }), signal });
  if (!response.ok) throw new Error('Поиск временно недоступен');
  const data: unknown = await response.json();
  if (!isSearchResponse(data)) throw new Error('Сервис вернул некорректный ответ');
  return data;
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
