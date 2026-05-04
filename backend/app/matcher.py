"""
Core matching logic.
Uses Qwen2.5-14B to analyze resume-JD fit and produce structured output.
"""
from typing import List, Optional

from .llm_client import get_llm_client
from .schemas import (
    AnalyzeResponse,
    DimensionScores,
    MatchEvidence,
    ResumeAnalysis,
    ResumeInput,
)


# ============================================================
# Prompts
# ============================================================

SYSTEM_PROMPT = """You are an expert technical recruiter and career coach. \
Your job is to analyze how well a candidate's resume matches a job description (JD), \
and produce a structured, fair, evidence-based assessment.

Be objective. Cite specific quotes from the resume and JD as evidence. \
Do not invent qualifications the candidate does not have. \
Do not penalize candidates for missing minor or stylistic preferences."""


SINGLE_MATCH_PROMPT_TEMPLATE = """Analyze how well the following resume matches the job description.

=== JOB DESCRIPTION ===
{jd}

=== RESUME ===
{resume}

=== TASK ===
Produce a JSON object with this exact structure:

{{
  "overall_score": <integer 0-100>,
  "dimension_scores": {{
    "skills": <integer 0-100, how well technical/soft skills match>,
    "experience": <integer 0-100, how well years and type of experience match>,
    "education": <integer 0-100, how well education level and field match>,
    "industry": <integer 0-100, how well industry/domain background matches>
  }},
  "strengths": [
    {{
      "point": "<one sentence describing a strength>",
      "resume_excerpt": "<short quote from resume supporting this>",
      "jd_excerpt": "<short quote from JD this matches>"
    }},
    ... (3-5 strengths total)
  ],
  "gaps": [
    {{
      "point": "<one sentence describing a gap or weakness>",
      "resume_excerpt": "<short quote from resume, or empty string if not applicable>",
      "jd_excerpt": "<short quote from JD requirement that's missing>"
    }},
    ... (2-4 gaps total)
  ],
  "summary": "<2-3 sentence overall assessment>"
}}

Scoring guide:
- 90-100: Exceptional fit, strongly recommended
- 75-89: Strong fit with minor gaps
- 60-74: Moderate fit, notable gaps
- 40-59: Weak fit, significant gaps
- 0-39: Poor fit, major mismatch

Return ONLY the JSON object, no other text."""


COMPARISON_PROMPT_TEMPLATE = """The user has uploaded multiple versions of their own resume \
and wants to know which version best fits this specific job description.

=== JOB DESCRIPTION (excerpt) ===
{jd_excerpt}

=== RESUME VERSIONS (analyzed) ===
{candidates_summary}

=== TASK ===
Recommend which version of their resume to submit for this job, and briefly explain why.

Return a JSON object:

{{
  "best_match_id": "<id of the recommended version>",
  "comparison_insight": "<2-3 sentences explaining why this version is the best fit for THIS specific job, and what makes it stronger than the others>"
}}

Return ONLY the JSON object."""


# ============================================================
# Core matching functions
# ============================================================

def match_single(resume: ResumeInput, jd: str) -> ResumeAnalysis:
    """
    Match one resume against one JD using LLM judge.

    Returns a structured ResumeAnalysis.
    """
    client = get_llm_client()

    prompt = SINGLE_MATCH_PROMPT_TEMPLATE.format(
        jd=jd.strip(),
        resume=resume.content.strip(),
    )

    raw = client.chat_json(
        prompt=prompt,
        system=SYSTEM_PROMPT,
        temperature=0.1,
    )

    # Parse into our schema
    return ResumeAnalysis(
        resume_id=resume.id,
        overall_score=int(raw["overall_score"]),
        dimension_scores=DimensionScores(**raw["dimension_scores"]),
        strengths=[MatchEvidence(**s) for s in raw.get("strengths", [])],
        gaps=[MatchEvidence(**g) for g in raw.get("gaps", [])],
        summary=raw.get("summary", ""),
    )


def compare_multiple(
    analyses: List[ResumeAnalysis],
    jd: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    When multiple resumes are analyzed, ask the LLM to pick the best
    and explain why.

    Returns:
        (best_match_id, comparison_insight) or (None, None) if only one resume.
    """
    if len(analyses) < 2:
        return None, None

    # Build candidates summary
    candidates_lines = []
    for a in analyses:
        candidates_lines.append(
            f"- ID: {a.resume_id}\n"
            f"  Overall: {a.overall_score}/100 "
            f"(skills={a.dimension_scores.skills}, "
            f"exp={a.dimension_scores.experience}, "
            f"edu={a.dimension_scores.education}, "
            f"industry={a.dimension_scores.industry})\n"
            f"  Summary: {a.summary}"
        )
    candidates_summary = "\n\n".join(candidates_lines)

    # Truncate JD for comparison context
    jd_excerpt = jd.strip()[:800]

    client = get_llm_client()
    prompt = COMPARISON_PROMPT_TEMPLATE.format(
        jd_excerpt=jd_excerpt,
        candidates_summary=candidates_summary,
    )

    try:
        raw = client.chat_json(prompt=prompt, temperature=0.1)
        return raw.get("best_match_id"), raw.get("comparison_insight")
    except Exception as e:
        # If comparison fails, fall back to highest score
        print(f"Comparison failed, falling back to highest score: {e}")
        best = max(analyses, key=lambda a: a.overall_score)
        return best.resume_id, None


def analyze(resumes: List[ResumeInput], jd: str) -> AnalyzeResponse:
    """
    Main entry point: analyze one or more resumes against a JD.

    Returns the full structured response.
    """
    if not resumes:
        raise ValueError("At least one resume is required")
    if not jd or not jd.strip():
        raise ValueError("JD cannot be empty")

    # Analyze each resume
    analyses = []
    for r in resumes:
        try:
            analysis = match_single(r, jd)
            analyses.append(analysis)
        except Exception as e:
            print(f"Failed to analyze resume {r.id}: {e}")
            # Skip failed ones rather than crash entire request
            continue

    if not analyses:
        raise ValueError("All resume analyses failed")

    # Sort by overall score, descending
    analyses.sort(key=lambda a: a.overall_score, reverse=True)

    # Multi-resume comparison
    best_match_id, comparison_insight = compare_multiple(analyses, jd)

    return AnalyzeResponse(
        results=analyses,
        best_match_id=best_match_id,
        comparison_insight=comparison_insight,
    )


# ============================================================
# Quick test
# ============================================================
if __name__ == "__main__":
    sample_resume = ResumeInput(
        id="test_1",
        content="""
        John Doe
        Software Engineer with 5 years of experience in Python and Django.
        Worked at TechCorp building backend APIs.
        BS in Computer Science from MIT, 2018.
        Skills: Python, Django, PostgreSQL, AWS, Docker.
        """,
        filename="test.pdf",
    )

    sample_jd = """
    Senior Backend Engineer
    We are looking for an experienced backend engineer to join our team.
    Requirements:
    - 4+ years of Python development
    - Experience with Django or Flask
    - Familiarity with cloud platforms (AWS preferred)
    - Strong knowledge of SQL databases
    - Bachelor's in CS or related field
    """

    print("Running single resume analysis...")
    print("(This will take 15-30 seconds)\n")

    response = analyze([sample_resume], sample_jd)

    print("=== Results ===")
    for r in response.results:
        print(f"\nResume {r.resume_id}: {r.overall_score}/100")
        print(f"  Skills: {r.dimension_scores.skills}")
        print(f"  Experience: {r.dimension_scores.experience}")
        print(f"  Education: {r.dimension_scores.education}")
        print(f"  Industry: {r.dimension_scores.industry}")
        print(f"\nSummary: {r.summary}")
        print(f"\nStrengths ({len(r.strengths)}):")
        for s in r.strengths:
            print(f"  - {s.point}")
        print(f"\nGaps ({len(r.gaps)}):")
        for g in r.gaps:
            print(f"  - {g.point}")