// Espejo de los esquemas Pydantic del backend (app/schemas).

export type Role = "ADMIN" | "RESIDENTE" | "AUXILIAR" | "CONTABILIDAD" | "CONSEJO";
export type AccessLevel = "ADMIN" | "PUBLIC";
export type Category =
  | "MANTENIMIENTO"
  | "ACTAS"
  | "CONTRATOS"
  | "FINANCIERO"
  | "CONVIVENCIA"
  | "COMUNICADOS"
  | "COTIZACIONES";
export type DocStatus = "UPLOADED" | "QUEUED" | "PROCESSING" | "READY" | "FAILED";
export type JobStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "RETRYING";

export interface User {
  id: string;
  email: string;
  full_name: string;
}

export interface Membership {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: Role;
}

export interface Me {
  user: User;
  memberships: Membership[];
}

export interface Job {
  id: string;
  status: JobStatus;
  current_step: string | null;
  attempts: number;
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface DocumentItem {
  id: string;
  title: string;
  original_filename: string;
  category: Category;
  access_level: AccessLevel;
  status: DocStatus;
  size_bytes: number;
  page_count: number | null;
  is_scanned: boolean | null;
  error_message: string | null;
  created_at: string;
  processed_at: string | null;
  job: Job | null;
}

export interface UploadResponse {
  document_id: string;
  upload_url: string;
  method: "PUT";
  headers: Record<string, string>;
  expires_in: number;
}

export interface Source {
  n: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_number: number;
  page_end: number;
  category: string;
  section_title: string | null;
  snippet?: string;
  content?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  citations: number[];
  status: "streaming" | "done" | "error";
  error?: string;
  retryable?: boolean;
  searchQuery?: string;
}

export type DeadlineType = "POLICY_EXPIRY" | "CONTRACT_END" | "MAINTENANCE" | "CERTIFICATION" | "OTHER";
export type DeadlineStatus = "PENDING_REVIEW" | "ACTIVE" | "DONE" | "DISMISSED";

export interface Deadline {
  id: string;
  document_id: string;
  document_title: string;
  title: string;
  type: DeadlineType;
  status: DeadlineStatus;
  due_date: string; // AAAA-MM-DD
  start_date: string | null;
  recurrence_months: number | null;
  provider_name: string | null;
  source_page: number | null;
  source_quote: string | null;
  confidence: number | null;
  reminder_days: number[];
  reviewed_at: string | null;
  created_at: string;
}

export interface DeadlinesResponse {
  deadlines: Deadline[];
  analyzing: { document_id: string; title: string; status: string }[];
}

export interface Sourced {
  value: string | number | null;
  page: number | null;
  quote: string | null;
  verified: boolean;
  computed?: boolean;
  rate?: number;
}

export interface QuoteRecord {
  provider_name: string;
  provider_tax_id: string | null;
  subtotal: Sourced;
  tax: Sourced;
  total: Sourced;
  warranty: Sourced;
  warranty_months: number | null;
  delivery: Sourced;
  delivery_days: number | null;
  delivery_business_days: boolean | null;
  payment_terms: Sourced;
  valid_until: Sourced;
  includes: string[];
  excludes: string[];
  items: { description: string; quantity: number | null; unit: string | null; total: number | null }[];
}

export interface QuoteAnalysis {
  summary: string;
  comparability_warnings: string[];
  assessments: { provider_name: string; strengths: string[]; weaknesses: string[] }[];
  recommendation: string;
}

export interface Comparison {
  id: string;
  title: string;
  status: JobStatus;
  created_at: string;
  model: string | null;
  progress: string | null;
  error: string | null;
  best: {
    total: string | null;
    warranty: string | null;
    delivery: string | null;
    min_total: number | null;
    max_total: number | null;
  } | null;
  analysis: QuoteAnalysis | null;
  documents: { document_id: string; document_title: string; provider_name: string | null; extracted: QuoteRecord | null }[];
}

export interface ComparisonSummary {
  id: string;
  title: string;
  status: JobStatus;
  created_at: string;
  providers: string[];
  min_total: number | null;
  progress: string | null;
}

export type TaskStatus = "OPEN" | "IN_PROGRESS" | "DONE";
export type MinutesState = "NONE" | "PROCESSING" | "READY" | "FAILED";

export interface Acta {
  document_id: string;
  title: string;
  document_date: string | null;
  created_at: string;
  status: MinutesState;
  error: string | null;
  assembly_type: string | null;
  assembly_date: string | null;
  quorum_pct: number | null;
  agreements: number;
  votes: number;
  open_tasks: number;
}

export interface MinutesTask {
  id: string;
  description: string;
  assignee: string | null;
  due_date: string | null;
  status: TaskStatus;
  source_page: number | null;
  document_id: string;
  document_title: string;
}

export interface Agreement {
  topic: string;
  decision: string;
  approved: boolean | null;
  page: number;
  quote: string;
  verified: boolean;
}

export interface Vote {
  topic: string;
  yes_pct: number | null;
  no_pct: number | null;
  abstain_pct: number | null;
  result: "APROBADO" | "NEGADO" | "SIN_DATO";
  page: number;
  quote: string;
  verified: boolean;
}

export interface MinutesDetail {
  document_id: string;
  title: string;
  status: MinutesState;
  error: string | null;
  assembly_type: string | null;
  assembly_date: string | null;
  quorum_pct: number | null;
  summary: string | null;
  agreements: Agreement[];
  votes: Vote[];
  model: string | null;
  tasks: MinutesTask[];
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
}

export interface StoredMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Source[];
  created_at: string;
}
