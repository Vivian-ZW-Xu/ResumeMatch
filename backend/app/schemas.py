"""
Pydantic schemas for request/response data structures.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


# ============================================================
# Input schemas
# ============================================================

class ResumeInput(BaseModel):
    """A single resume input."""
    id: str = Field(..., description="Unique identifier for this resume")
    content: str = Field(..., description="Plain text content of the resume")
    filename: Optional[str] = Field(None, description="Original filename if uploaded")


class AnalyzeRequest(BaseModel):
    """Request body for /analyze endpoint."""
    resumes: List[ResumeInput] = Field(..., description="One or more resumes to analyze")
    jd: str = Field(..., description="Job description text")


# ============================================================
# Output schemas
# ============================================================

class DimensionScores(BaseModel):
    """Scores broken down by matching dimension."""
    skills: int = Field(..., ge=0, le=100, description="Skill match score (0-100)")
    experience: int = Field(..., ge=0, le=100, description="Experience match score (0-100)")
    education: int = Field(..., ge=0, le=100, description="Education match score (0-100)")
    industry: int = Field(..., ge=0, le=100, description="Industry/domain match score (0-100)")


class MatchEvidence(BaseModel):
    """A piece of evidence supporting strength or gap."""
    point: str = Field(..., description="Description of the strength or gap")
    resume_excerpt: Optional[str] = Field(None, description="Quote from resume")
    jd_excerpt: Optional[str] = Field(None, description="Quote from JD")


class ResumeAnalysis(BaseModel):
    """Full analysis result for a single resume."""
    resume_id: str
    overall_score: int = Field(..., ge=0, le=100)
    dimension_scores: DimensionScores
    strengths: List[MatchEvidence] = Field(default_factory=list)
    gaps: List[MatchEvidence] = Field(default_factory=list)
    summary: str = Field(..., description="Overall 2-3 sentence summary")
    resume_content: str = Field(default="", description="Original resume text (for follow-up suggestions)")

# ============================================================
# JD Summary schemas
# ============================================================

class JDSummary(BaseModel):
    """Structured summary extracted from a job description."""
    company: Optional[str] = Field(None, description="Company name")
    title: Optional[str] = Field(None, description="Job title")
    location: Optional[str] = Field(None, description="Location (city, remote, hybrid, etc.)")
    employment_type: Optional[str] = Field(None, description="Full-time / Part-time / Internship / Contract")
    duration: Optional[str] = Field(None, description="Duration if applicable (e.g. '12 weeks' for internship)")
    salary: Optional[str] = Field(None, description="Salary range if mentioned")
    education: Optional[str] = Field(None, description="Education requirement")
    key_skills: List[str] = Field(default_factory=list, description="Top 3-5 required technical skills")
    work_mode: Optional[str] = Field(None, description="Onsite / Hybrid / Remote")
    
class AnalyzeResponse(BaseModel):
    """Response for /analyze endpoint."""
    results: List[ResumeAnalysis]
    best_match_id: Optional[str] = Field(None, description="ID of best-matching resume (only when multiple resumes)")
    comparison_insight: Optional[str] = Field(None, description="LLM-generated comparison summary (only when multiple)")
    jd_summary: Optional[JDSummary] = Field(None, description="Structured summary of the job description")


# ============================================================
# Suggest endpoint schemas
# ============================================================

class SuggestRequest(BaseModel):
    """Request body for /suggest endpoint."""
    resume_content: str = Field(..., description="Full resume text")
    jd: str = Field(..., description="Job description text")
    gap_point: str = Field(..., description="The specific gap to address")
    gap_jd_excerpt: Optional[str] = Field(None, description="JD requirement that's missing")
    gap_resume_excerpt: Optional[str] = Field(None, description="Resume excerpt related to gap")


class SuggestResponse(BaseModel):
    """Response for /suggest endpoint."""
    suggestion: str = Field(..., description="Concrete actionable advice")
    rewritten_bullet: Optional[str] = Field(None, description="Suggested rewritten resume bullet, if applicable")
