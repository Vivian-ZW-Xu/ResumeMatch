# ResumeMatch

> **Find which version of your resume best matches a job description — in seconds.**

🌐 **Live demo**: [resumematch.pages.dev](https://resumematch.pages.dev)
📄 **Report**: [ResumeMatch_Report.md](./ResumeMatch_Report.md)

---

## What it does

Job descriptions are long. ResumeMatch turns a JD into a structured, evidence-backed answer to the question every applicant actually has: *Does my resume fit this role, and where are the gaps?*

Two ways to use it:

1. **Single resume + JD** → Quick fit assessment with strengths, gaps, and concrete improvement suggestions.
2. **Multiple resume versions + JD** → Ranks your resumes (e.g. Data Scientist version vs. ML Engineer version) and tells you which framing is the strongest fit, with cited evidence.

For each resume the system produces:

- An overall match score (0–100) and dimension scores across **Skills / Experience / Education / Industry**
- A custom rubric (6–9 criteria) generated specifically for the JD, with `yes / partial / no` verdicts and evidence excerpts
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

> **Note**: Custom resume uploads (your own PDFs) require the local backend to be running. See setup below.

---

## How it works (high level)

```
PDF Parser → JD Extractor → Rubric Generator → Per-Resume Matcher
                                                       ↓
                                          Deterministic Scoring → Ranking
                                                       ↓
                                          Comparison & Suggestions
```

- **PDF parsing**: pdfplumber with PyMuPDF fallback
- **JD extraction**: LLM produces a structured JSON summary + a custom evaluation rubric tailored to the specific JD
- **Per-resume matching**: For each rubric criterion, the LLM returns `yes / partial / no` with cited evidence
- **Scoring**: Deterministic in Python (verdicts → weighted scores per dimension), so identical inputs always produce identical scores
- **All LLM calls run locally** via Ollama (Qwen 2.5 14B). No API keys, no data leaving your machine.

Full design discussion in the [report](./ResumeMatch_Report.md).

---

## Run it locally

### Prerequisites

- macOS or Linux (tested on Apple Silicon)
- ~9 GB free disk for the LLM
- 16 GB+ RAM
- Python 3.11
- Node.js 20+

### Step 1 — Install Ollama and pull the model

```bash
brew install ollama
brew services start ollama
ollama pull qwen2.5:14b
```

Verify the model is available:

```bash
ollama list
# should show qwen2.5:14b
```

### Step 2 — Backend

```bash
cd backend
conda create -n resume-match python=3.11 -y
conda activate resume-match
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Backend runs at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Step 3 — Frontend

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

That's it — upload your resume, paste a JD, click Analyze.

---

## Project structure

```
ResumeMatch/
├── backend/
│   └── app/
│       ├── main.py            # FastAPI entry point + CORS
│       ├── matcher.py         # Core matching logic, prompts, scoring
│       ├── llm_client.py      # Ollama wrapper
│       ├── pdf_parser.py      # PDF text extraction
│       └── schemas.py         # Pydantic response models
├── frontend/
│   ├── app/                   # Next.js App Router
│   ├── components/
│   │   └── resume-match/      # Domain components (uploader, result card, JD summary)
│   ├── lib/                   # API client + utilities
│   └── public/samples/        # Sample resumes, sample JD, cached sample response
├── ResumeMatch_Report.md      # Full project report
└── README.md                  # This file
```

---

## Tech stack

| Layer | Tech |
|---|---|
| LLM | Qwen 2.5 14B (Q4) via local Ollama |
| Backend | FastAPI + Pydantic + pdfplumber |
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui |
| Visualization | Recharts (radar charts) |
| Hosting | Cloudflare Pages (frontend, static export) |

---

## Limitations

- Analysis takes 1–3 minutes per resume on M4 Max — the model is local, not API-backed
- The frontend is permanently online but the backend runs locally; the live deployed demo serves a cached response for the sample case so it works without the backend running
- LLM occasionally generates rubric items that conflate nice-to-haves with hard requirements (mitigated by prompt design but not eliminated)
- English-only

See the [report](./ResumeMatch_Report.md) for the full discussion + future work.

---

## Author

Zhuwei (Vivian) Xu — NYU Data Science M.S.
NYU Text as Data, Spring 2026 (Prof. Elliott Ash)

Built with [Claude](https://claude.ai) as a pair-programming assistant.
