/**
 * API client for ResumeMatch backend.
 * Wraps axios calls with type safety.
 */
import axios from "axios";

// ============================================================
// Types (mirror backend schemas)
// ============================================================

export interface DimensionScores {
  skills: number;
  experience: number;
  education: number;
  industry: number;
}

export interface MatchEvidence {
  point: string;
  resume_excerpt?: string | null;
  jd_excerpt?: string | null;
}

// ============================================================
// Rubric types (new — for rubric-based scoring)
// ============================================================

export type RubricDimension = "skills" | "experience" | "education" | "industry";
export type RubricVerdict = "yes" | "partial" | "no";

export interface RubricItem {
  id: string;
  criterion: string;
  dimension: RubricDimension;
  weight: number;
}

export interface RubricResult {
  id: string;
  criterion: string;
  verdict: RubricVerdict;
  evidence?: string | null;
  reasoning?: string | null;
}

export interface JDRequirements {
  hard_requirements: string[];
  nice_to_haves: string[];
  job_duties: string[];
  not_required: string[];
  evaluation_rubric: RubricItem[];
}

// ============================================================
// Analysis result types
// ============================================================

export interface ResumeAnalysis {
  resume_id: string;
  overall_score: number;
  dimension_scores: DimensionScores;
  strengths: MatchEvidence[];
  gaps: MatchEvidence[];
  summary: string;
  resume_content: string;
  rubric_results: RubricResult[];
}

export interface JDSummary {
  company?: string | null;
  company_brief?: string | null;
  title?: string | null;
  location?: string | null;
  employment_type?: string | null;
  duration?: string | null;
  salary?: string | null;
  education?: string | null;
  key_skills: string[];
  work_mode?: string | null;
}

export interface AnalyzeResponse {
  results: ResumeAnalysis[];
  best_match_id?: string | null;
  comparison_insight?: string | null;
  jd_summary?: JDSummary | null;
  jd_requirements?: JDRequirements | null;
}

// ============================================================
// API client
// ============================================================

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 300000, // 5 minutes - LLM can be slow
  headers: {
    "ngrok-skip-browser-warning": "true",
  },
});

/**
 * Analyze resumes (PDF files) against a JD.
 */
export async function analyzeUpload(
  files: File[],
  jd: string
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("jd", jd);
  files.forEach((file) => {
    formData.append("files", file);
  });

  const response = await apiClient.post<AnalyzeResponse>(
    "/analyze/upload",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
        "ngrok-skip-browser-warning": "true",
      },
    }
  );

  return response.data;
}

/**
 * Analyze resumes (already-extracted text) against a JD.
 */
export async function analyzeText(
  resumes: { id: string; content: string; filename?: string }[],
  jd: string
): Promise<AnalyzeResponse> {
  const response = await apiClient.post<AnalyzeResponse>("/analyze", {
    resumes,
    jd,
  });
  return response.data;
}

/**
 * Health check.
 */
export async function checkHealth(): Promise<{ status: string }> {
  const response = await apiClient.get<{ status: string }>("/health");
  return response.data;
}

// ============================================================
// Suggest endpoint
// ============================================================

export interface SuggestRequest {
  resume_content: string;
  jd: string;
  gap_point: string;
  gap_jd_excerpt?: string | null;
  gap_resume_excerpt?: string | null;
}

export interface SuggestResponse {
  suggestion: string;
  rewritten_bullet?: string | null;
}

/**
 * Get an improvement suggestion for a specific gap.
 */
export async function suggestImprovement(
  request: SuggestRequest
): Promise<SuggestResponse> {
  const response = await apiClient.post<SuggestResponse>("/suggest", request);
  return response.data;
}