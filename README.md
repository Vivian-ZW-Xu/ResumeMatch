# ResumeMatch

> **Find which version of your resume best matches a job description — in seconds.**

🌐 **Live demo**: [resumematch.pages.dev](https://resumematch.pages.dev)
📄 **Report**: [ResumeMatch_Report.pdf](./ResumeMatch_Report.pdf)

---

## Recent Updates (May 12, 2026)

**v2 Deployment & Pipeline Upgrade.** The system has been migrated from
local Ollama (Qwen 2.5 14B) to a fully cloud-hosted setup:

- **Backend**: Now running on **Render** (free tier, 24/7) with
  **Groq-served Llama 3.3 70B** for inference. End-to-end analysis
  latency dropped from 1–3 minutes to 6–16 seconds (15–30× speedup).
- **Frontend**: Continues to be served from **Cloudflare Pages** with
  the API base URL hard-coded to the Render service.
- **Sample case**: The "Try with sample data" path is served from a
  pre-computed JSON file and renders in under 2 seconds, independent
  of backend availability.

**Pipeline Improvements.** Beyond the infrastructure migration, the
matching pipeline was refined through six iterations documented in
the report. Highlights:

- **Compound splitting**: Hard requirements written as conjunctions
  in the JD are now split into atomic rubric items.
- **Duty-to-experience proxy**: Technical-core responsibilities are
  transformed into past-experience rubric items, so the rubric
  captures the JD's strongest signals (not just the qualifications
  section).
- **Post-hoc rubric self-audit**: A second LLM pass audits the
  generated rubric for four common failure modes
  (`NICE_TO_HAVE_AS_HARD`, `JOB_DUTY_AS_REQUIREMENT`,
  `UNREASONABLE_THRESHOLD`, `NOT_IN_JD`) and removes or demotes
  problematic items.

**Honest limitations.** Rubric quality is JD-style sensitive. On JDs
where the candidate's resume variants differ along the JD's axes
(e.g., TikTok recsys JD with MLE vs DataScientist resumes), the system
produces strongly differentiating output (13-point spread). On JDs
where neither resume variant has the depth signals the JD demands
(e.g., ByteDance ML-infra JD asking for LLM fine-tuning / ModelOps /
GPU orchestration), the system honestly returns a small spread —
which is correct behavior, not a failure. See [ResumeMatch_Report.pdf](./ResumeMatch_Report.pdf)
for the full discussion.

---

## What it does

Job descriptions are long. ResumeMatch turns a JD into a structured, evidence-backed answer to the question every applicant actually has: *Does my resume fit this role, and where are the gaps?*

Two ways to use it:

1. **Single resume + JD** → Quick fit assessment with strengths, gaps, and concrete improvement suggestions.
2. **Multiple resume versions + JD** → Ranks your resumes (e.g. Data Scientist version vs. ML Engineer version) and tells you which framing is the strongest fit, with cited evidence.

For each resume the system produces:

- An overall match score (0–100) and dimension scores across **Skills / Experience / Education / Industry**
- A custom rubric (7–9 criteria) generated specifically for the JD, with `yes / partial / no` verdicts and evidence excerpts, plus a post-hoc self-audit pass that prunes flawed items
- **Strengths** — each linked to a JD requirement and a resume passage that satisfies it
- **Gaps** — each linked to a JD requirement, with on-demand suggestions and bullet rewrites
- A **Best Version** recommendation when multiple resumes are compared

---

## Try it without installing anything

1. Open **[resumematch.pages.dev](https://resumematch.pages.dev)**
2. Click **Try with sample data** — loads two pre-included resume versions (Data Scientist + ML Engineer) and a real TikTok ML Engineer Intern JD
3. Click **Analyze Match**
4. Explore the JD summary card, ranked results, rubric evaluation, strengths, gaps, and suggestions

The sample case runs entirely client-side and is always available. No setup, no signup.

> **Note**: Custom resume uploads (your own PDFs) hit the live Render-hosted backend, so they work without any local setup. The first upload after 15 min of idle may take 30–60 s while Render's free-tier instance cold-starts; subsequent calls are fast (6–16 s).

---

## How it works (high level)

```
PDF Parser → JD Extractor → Rubric Generator → Rubric Self-Audit → Per-Resume Matcher
                                                                          ↓
                                                       Deterministic Scoring → Ranking
                                                                          ↓
                                                       Comparison & Suggestions
```

- **PDF parsing**: pdfplumber with PyMuPDF fallback
- **JD extraction**: LLM produces a structured JSON summary + a custom evaluation rubric tailored to the specific JD
- **Rubric self-audit**: a second LLM pass reviews the generated rubric and removes / down-weights items that fail any of four checks (`NICE_TO_HAVE_AS_HARD`, `JOB_DUTY_AS_REQUIREMENT`, `UNREASONABLE_THRESHOLD`, `NOT_IN_JD`)
- **Per-resume matching**: For each rubric criterion, the LLM returns `yes / partial / no` with cited evidence
- **Scoring**: Deterministic in Python (verdicts → weighted scores per dimension), so identical inputs always produce identical scores
- **LLM inference** runs on **Groq-served Llama 3.3 70B**. Each `analyze()` call issues at minimum 4 LLM calls (JD parse, rubric self-audit, JD summary, per-resume rubric eval); plus 1 additional call per extra resume and 1 final cross-resume comparison call when ≥2 resumes are analyzed. End-to-end latency is 6–16 seconds.

Full design discussion in the [report](./ResumeMatch_Report.pdf).

---

## Run it locally

### Prerequisites

- macOS, Linux, or Windows (WSL)
- Python 3.11
- Node.js 20+
- A Groq API key (free tier works) — get one at [console.groq.com/keys](https://console.groq.com/keys)

### Setup

```bash
# 1. Get a Groq API key from https://console.groq.com
export GROQ_API_KEY=gsk_...

# 2. Backend
cd backend
conda create -n resume-match python=3.11 -y
conda activate resume-match
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Backend runs at `http://localhost:8000` (Swagger docs at `/docs`).
Frontend runs at `http://localhost:3000`.

Open the frontend, upload a resume PDF, paste a JD, click Analyze.

---

## Project structure

```
ResumeMatch/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point + CORS
│   │   ├── matcher.py         # Core matching logic, prompts, scoring, rubric audit
│   │   ├── llm_client.py      # Groq client wrapper
│   │   ├── pdf_parser.py      # PDF text extraction (pdfplumber + PyMuPDF fallback)
│   │   └── schemas.py         # Pydantic request / response models
│   ├── requirements.txt       # Production dependencies (deployed to Render)
│   └── requirements-dev.txt   # Notebook / experiments dependencies (not deployed)
├── frontend/
│   ├── app/                   # Next.js App Router
│   ├── components/
│   │   └── resume-match/      # Domain components (uploader, result card, JD summary)
│   ├── lib/                   # API client + utilities
│   └── public/samples/        # Sample resumes, sample JD, cached sample response
├── render.yaml                # Render Blueprint for backend deployment
├── ResumeMatch_Report.pdf     # Full project report
└── README.md                  # This file
```

---

## Tech stack

| Layer | Tech |
|---|---|
| LLM | Llama 3.3 70B (via Groq API) |
| Backend | FastAPI + Pydantic + pdfplumber |
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui |
| Visualization | Recharts (radar charts) |
| Frontend hosting | Cloudflare Pages (static export) |
| Backend hosting | Render (free tier) |

---

## Limitations

- End-to-end analysis takes 6–16 seconds via Groq (vs. 1–3 min on the local-Ollama v1 setup). Render's free tier cold-starts add 30–60 seconds after 15 min of idle.
- Groq free tier has a daily token limit (~100k tokens/day). Heavy traffic can hit it; the sample case is served from a cached JSON so it stays available regardless.
- LLM occasionally generates rubric items that conflate nice-to-haves with hard requirements (mitigated by the post-hoc rubric self-audit but not eliminated).
- Rubric quality is sensitive to JD phrasing — JDs that bury technical signals in non-`Responsibilities` prose can produce shallower rubrics.
- English-only.

See the [report](./ResumeMatch_Report.pdf) for the full discussion + future work.

---

## Author

Zhuwei (Vivian) Xu — NYU Data Science M.S.
NYU Text as Data, Spring 2026 (Prof. Elliott Ash)

Built with [Claude](https://claude.ai) as a pair-programming assistant.
