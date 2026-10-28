export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  role: string;
  organization_id: string;
}

export interface CollectionOut {
  id: string;
  name: string;
  slug: string;
  description: string;
  visibility: string;
  category: string;
  owner_id: string;
  document_count: number;
}

export interface DocumentOut {
  id: string;
  title: string;
  source_type: string;
  source_url: string;
  author: string;
  status: string;
  chunk_count: number;
  byte_size: number;
  content_hash: string;
  is_duplicate: boolean;
  duplicate_of_id: string | null;
  extraction_error: string;
  embedding_model: string;
  embedding_version: string;
  summary: string;
  collection_ids: string[];
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface Evidence {
  document_id: string;
  chunk_id: string;
  title: string;
  source_url: string;
  source_type: string;
  text: string;
  page_number: number | null;
  section_heading: string;
  retrieval_method: string;
  score: number;
  collection_ids: string[];
}

export interface SearchResponse {
  query: string;
  count: number;
  results: Evidence[];
}

export interface AnswerResponse {
  query: string;
  answer: string;
  insufficient_evidence: boolean;
  cited_labels: string[];
  evidence: Evidence[];
  model: { name: string; available: boolean };
  model_error: string;
}

export interface JobOut {
  id: string;
  document_id: string;
  state: string;
  progress: number;
  detail: string;
  error: string;
  attempts: number;
  updated_at: string | null;
}

export interface ApiKeyOut {
  id: string;
  name: string;
  prefix: string;
  scoped_collection_ids: string[];
  rate_limit_per_minute: number;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  usage_count: number;
  created_at: string | null;
  api_key?: string;
}

export interface DashboardStats {
  total_documents: number;
  documents_by_status: Record<string, number>;
  collections: number;
  jobs_by_state: Record<string, number>;
  total_chunks: number;
  recent_documents: { id: string; title: string; status: string; created_at: string | null }[];
  failed_jobs: { document_id: string; error: string; updated_at: string | null }[];
  recent_searches: { action: string; detail: string; created_at: string | null }[];
}

export interface ModelStatus {
  generation: {
    provider: string;
    model: string;
    available: boolean;
    detail: string;
    context_tokens: number;
    max_output_tokens: number;
    outbound_disabled: boolean;
    last_checked: string;
  };
  embedding: { provider: string; model: string; version: string; dim: number };
  vector_store: string;
}


export interface ConversationOut {
  id: string;
  title: string;
  collection_ids: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Evidence[];
  created_at: string | null;
}

