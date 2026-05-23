export type Mode = "list" | "summarize" | "generate";
export type Confidence = "high" | "medium" | "low";

export interface Source {
  position: number;
  doc_id: string;
  title: string;
  short_name: string;
  section_path?: string | null;
  page?: number | null;
  url?: string | null;
  quote?: string | null;
  score: number;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  embedding_tokens: number;
  estimated_cost_usd: number;
  calls: unknown[];
}

export interface AskResponse {
  query_id: string;
  answer: string;
  mode: Mode;
  confidence: Confidence;
  intent: string;
  decontextualized_query?: string | null;
  sources: Source[];
  scope: { jurisdictions: string[] };
  token_usage: TokenUsage;
  model: string;
  elapsed_ms: number;
  retrieval: { candidates: number; reranked: number; fusion: string };
}

export interface CorpusDoc {
  id: string;
  title: string;
  short_name: string;
  jurisdiction: string;
  framework_family: string;
  status: string;
  version_date: string;
  official_url: string;
  source_type: string;
}

export interface CorpusTier {
  id: string;
  name: string;
  blurb: string;
  documents: CorpusDoc[];
}

export interface Corpus {
  stats: { frameworks: number; documents: number };
  jurisdictions: Record<string, string>;
  tiers: CorpusTier[];
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  response?: AskResponse;
  streaming?: boolean; // true while answer deltas are still arriving (SSE)
}
