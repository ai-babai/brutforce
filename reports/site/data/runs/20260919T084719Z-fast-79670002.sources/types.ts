export type Scenario = 'exact' | 'uncertain' | 'none' | 'error';
export type Candidate = { id: string; name: string; winery: string; year: number; image: string; description: string };
export type SearchResponse = { demo: true; candidates: Candidate[]; selectedId?: string };
