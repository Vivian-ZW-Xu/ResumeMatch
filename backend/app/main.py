"""
ResumeMatch Backend
Main FastAPI application entry point.
"""
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from .matcher import analyze
from .pdf_parser import parse_pdf
from .schemas import AnalyzeRequest, AnalyzeResponse, ResumeInput


app = FastAPI(
    title="ResumeMatch API",
    description="Resume-JD matching system with multi-method NLP comparison",
    version="0.1.0",
)

# CORS: allow frontend to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "name": "ResumeMatch API",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# Analysis endpoints
# ============================================================

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(request: AnalyzeRequest):
    """
    Analyze one or more resumes against a job description.

    Accepts JSON with already-extracted resume text.
    For PDF uploads, use /analyze/upload instead.
    """
    try:
        return analyze(request.resumes, request.jd)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@app.post("/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(
    jd: str = Form(...),
    files: List[UploadFile] = File(...),
):
    """
    Analyze uploaded resume PDFs against a JD.

    Frontend will primarily use this endpoint.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one resume file required")
    if not jd or not jd.strip():
        raise HTTPException(status_code=400, detail="JD cannot be empty")

    resumes = []
    for idx, file in enumerate(files):
        try:
            content = await file.read()
            text = parse_pdf(content)
            resumes.append(
                ResumeInput(
                    id=f"resume_{idx + 1}",
                    content=text,
                    filename=file.filename,
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse {file.filename}: {e}",
            )

    try:
        return analyze(resumes, jd)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")