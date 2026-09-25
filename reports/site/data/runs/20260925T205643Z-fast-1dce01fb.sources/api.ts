import type { CatalogResponse, Candidate, FeedbackDecision, FeedbackReceipt, PhotoReceipt, RecommendationResponse, Scenario, SearchResponse } from './types';

export class InvalidPhotoError extends Error {
  constructor() { super('Не удалось прочитать изображение. Выберите другое фото.'); this.name = 'InvalidPhotoError'; }
}

export class StaleCatalogCursorError extends Error {
  constructor() { super('Каталог обновился. Обновите результаты.'); this.name = 'StaleCatalogCursorError'; }
}

export async function searchWine(scenario: Scenario, query?: string, signal?: AbortSignal, photoId?: string): Promise<SearchResponse> {
  const response = await fetch('/v1/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario, ...(query ? { query } : {}), ...(photoId ? { photoId } : {}) }), signal });
  if (!response.ok) throw new Error('Поиск временно недоступен');
  const data: unknown = await response.json();
  if (!isSearchResponse(data)) throw new Error('Сервис вернул некорректный ответ');
  return data;
}

export async function uploadPhoto(file: File, signal?: AbortSignal): Promise<PhotoReceipt> {
  const form = new FormData(); form.append('photo',file);
  const response=await fetch('/v1/photos',{method:'POST',body:form,signal});
  if(!response.ok){
    if([400,413,415].includes(response.status)){
      const problem=await response.json().catch(()=>null);
      if(response.status===413||response.status===415||['invalid_photo','invalid_upload'].includes(problem?.error?.code))throw new InvalidPhotoError();
    }
    throw new Error('Не удалось загрузить фотографию');
  }
  const value:unknown=await response.json();
  if(!isPhotoReceipt(value))throw new Error('Сервис вернул некорректную квитанцию');
  return value;
}

export async function getCatalog({ limit = 24, cursor, q, signal }: { limit?: number; cursor?: string; q?: string; signal?: AbortSignal } = {}):Promise<CatalogResponse>{
  const params = new URLSearchParams({ limit: String(limit), cursor: cursor ?? '', q: q ?? '' });
  const response=await fetch(`/v2/catalog?${params}`,{signal});
  if(response.status===409)throw new StaleCatalogCursorError();
  if(!response.ok)throw new Error('Каталог временно недоступен');
  const data:unknown=await response.json();
  if(!isCatalogResponse(data)||new Set(data.candidates.map(item=>item.id)).size!==data.candidates.length)throw new Error('Каталог вернул некорректные данные');
  return data;
}

export async function getRecommendations(wineId: string, signal?: AbortSignal): Promise<RecommendationResponse> {
  const response = await fetch('/v1/recommendations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ wineId, limit: 3 }),
    signal,
  });
  if (!response.ok) throw new Error('Рекомендации временно недоступны');
  const data: unknown = await response.json();
  if (!isRecommendationResponse(data)) throw new Error('Сервис вернул некорректные рекомендации');
  return data;
}

export async function savePhotoFeedback(input: {
  feedbackToken: string;
  idempotencyKey: string;
  decision: FeedbackDecision;
  displayedWineId?: string;
  correctWineId?: string;
  comment?: string;
}, signal?: AbortSignal): Promise<FeedbackReceipt> {
  const response = await fetch('/v1/feedback', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) throw new Error(response.status === 409 ? 'Эта разметка конфликтует с уже сохранённой.' : 'Не удалось сохранить разметку. Попробуйте ещё раз.');
  const data: unknown = await response.json();
  if (!isFeedbackReceipt(data)) throw new Error('Сервис вернул некорректную квитанцию разметки.');
  return data;
}

function isPhotoReceipt(value:unknown):value is PhotoReceipt{
  if(!value||typeof value!=='object')return false; const v=value as Record<string,unknown>;
  return typeof v.id==='string'&&/^[a-f0-9]{32}$/.test(v.id)&&typeof v.createdAt==='string'&&typeof v.mime==='string'&&['bytes','width','height'].every(k=>typeof v[k]==='number'&&Number.isInteger(v[k])&&(v[k] as number)>0);
}

function isSearchResponse(value: unknown): value is SearchResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  if (typeof data.demo !== 'boolean' || !Array.isArray(data.candidates)) return false;
  const validCandidates = data.candidates.every(candidate => {
    if (!candidate || typeof candidate !== 'object') return false;
    const item = candidate as Record<string, unknown>;
    return isCandidate(item);
  });
  if (!validCandidates) return false;
  if (data.selectedId !== undefined && (
    typeof data.selectedId !== 'string'
    || !data.candidates.some(candidate => candidate.id === data.selectedId)
  )) return false;
  if (data.action !== undefined && (
    typeof data.action !== 'string'
    || ![
      'no_match',
      'insufficient_information',
      'outside_display_catalog',
      'partial_display_catalog',
    ].includes(data.action)
  )) return false;
  if (['recognizedSlug', 'catalogVersion', 'recognitionCatalogVersion', 'modelVersion', 'feedbackToken'].some(
    key => data[key] !== undefined && typeof data[key] !== 'string',
  )) return false;
  if (data.feedbackToken !== undefined && !/^[a-f0-9]{32}$/.test(data.feedbackToken as string)) return false;
  if (data.action === 'outside_display_catalog' && data.candidates.length !== 0) return false;
  return true;
}

function isFeedbackReceipt(value: unknown): value is FeedbackReceipt {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return typeof item.feedbackId === 'string' && /^[a-f0-9]{32}$/.test(item.feedbackId)
    && typeof item.createdAt === 'string' && item.reviewStatus === 'pending_review'
    && typeof item.duplicate === 'boolean';
}

function isRecommendationResponse(value: unknown): value is RecommendationResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return typeof data.demo === 'boolean'
    && Array.isArray(data.candidates)
    && data.candidates.every(isCandidate)
    && ['catalogVersion', 'modelVersion'].every(
      key => data[key] === undefined || typeof data[key] === 'string',
    );
}

function isCatalogResponse(value: unknown): value is CatalogResponse {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return typeof data.demo === 'boolean'
    && typeof data.catalogVersion === 'string'
    && (data.nextCursor === undefined || typeof data.nextCursor === 'string')
    && Array.isArray(data.candidates)
    && data.candidates.every(isCandidate);
}

function isCandidate(candidate: unknown): candidate is Record<string, unknown> {
  if (!candidate || typeof candidate !== 'object') return false;
  const item = candidate as Record<string, unknown>;
  return ['id','name','winery','image','description'].every(key => typeof item[key] === 'string')
    && ['line', 'color', 'sugar'].every(
      key => item[key] === undefined || typeof item[key] === 'string',
    )
    && (item.year === undefined || (typeof item.year === 'number' && Number.isInteger(item.year)))
    && ['sourceSnapshotDate', 'categoryAndSweetness'].every(key => item[key] === undefined || typeof item[key] === 'string')
    && (item.sourceUrl === undefined || (typeof item.sourceUrl === 'string' && isHTTPURL(item.sourceUrl)))
    && ['alcoholPercent', 'alcoholMinPercent', 'alcoholMaxPercent', 'volumeL'].every(key => item[key] === undefined || typeof item[key] === 'number')
    && ['region', 'grapes'].every(key => item[key] === undefined || (Array.isArray(item[key]) && item[key].every(value => typeof value === 'string')))
    && (item.ratings === undefined || (Array.isArray(item.ratings) && item.ratings.every(rating => rating && typeof rating === 'object' && typeof (rating as Record<string, unknown>).kind === 'string' && typeof (rating as Record<string, unknown>).source_text === 'string')))
    && (item.imageVariants === undefined || (Array.isArray(item.imageVariants) && item.imageVariants.every(variant => isImageVariant(variant))));
}

function isHTTPURL(value: string): boolean {
  try { return ["http:", "https:"].includes(new URL(value).protocol); } catch { return false; }
}

function isImageVariant(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const variant = value as Record<string, unknown>;
  return ['role', 'path', 'mimeType', 'sha256'].every(key => typeof variant[key] === 'string')
    && ['width', 'height', 'bytes'].every(key => typeof variant[key] === 'number' && Number.isInteger(variant[key]) && (variant[key] as number) > 0);
}
