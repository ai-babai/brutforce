export type Scenario = 'exact' | 'uncertain' | 'none' | 'error';
export type Candidate = {
  id: string;
  name: string;
  description: string;
  winery: string;
  year: number;
  image: string;
  line?: string;
  color?: string;
  sugar?: string;
};
export type SearchResponse = { demo: true; candidates: Candidate[]; selectedId?: string };
export type RecommendationResponse = { demo: boolean; candidates: Candidate[]; catalogVersion?: string; modelVersion?: string };
export type PhotoReceipt = { id: string; createdAt: string; bytes: number; mime: string; width: number; height: number };
