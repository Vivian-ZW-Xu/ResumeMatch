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

CORE PRINCIPLES:
1. Read both the JD and the resume CAREFULLY before judging. Do not skim.
2. Be objective and evidence-based. Cite specific quotes.
3. Do not invent qualifications the candidate does not have.

WHAT COUNTS AS A REAL GAP:
A gap is ONLY valid if BOTH conditions are true:
(a) The JD explicitly lists this as a HARD REQUIREMENT (not optional, not a perk, \
not a post-hire activity), AND
(b) The resume clearly does NOT contain this qualification, even after careful reading.

WHAT IS NOT A GAP — DO NOT LIST THESE AS GAPS:

1. Things the JD says are NOT required.
   Example phrases: "you don't need X", "X is not required", "X is nice to have, but not required".
   Specifically: if the JD says "you don't need a background in finance", \
   then lacking finance is NOT a gap.

2. Onboarding activities, perks, or post-hire participation.
   Example phrases: "join our reading circles", "attend our seminars", "participate in our events", \
   "engage with our team". These are things the candidate would do AFTER being hired, \
   so they are NOT requirements the resume should already prove.

3. Soft preferences.
   Phrases that signal preference, NOT requirement: "preferred", "is a plus", "we value", \
   "bonus", "nice to have", "ideal candidate would have".

4. Things the resume actually DOES have but you missed.
   Before listing a gap, search the resume one more time. Examples:
   - If the JD asks for "research projects" and the resume mentions "papers presented at NeurIPS" \
   or "co-authored 2 papers" — that IS research, do NOT claim it's missing.
   - If the resume says "Python (5+ years)", do NOT say "duration unspecified".
   - If the resume mentions specific projects, do NOT claim "no project experience".

VERIFICATION BEFORE LISTING ANY GAP:
For each gap you draft, ask yourself these questions:
- Is this phrased in the JD as a HARD requirement, not a preference or perk?
- Did I re-read the entire resume to confirm it's missing?
- Could a reasonable recruiter agree this is a real concern?
If you have any doubt on any of these, REMOVE that gap.

OTHER RULES:
- Strengths must directly address something the JD asks for. \
Do not list resume highlights that aren't relevant to this JD.
- The Industry score reflects domain alignment. \
If the JD does not specify a particular industry, score Industry at 70+ \
(not low) — because there's no domain mismatch to penalize.

SCORING — USE THE FULL RANGE:
Avoid clustering all candidates in a narrow band. Use the full 0-100 scale:
- 90-100: Exceptional fit — meets all hard requirements + standout strengths.
- 75-89: Strong fit — meets all hard requirements with some standout areas.
- 60-74: Moderate fit — meets most hard requirements but with notable gaps.
- 40-59: Weak fit — missing several hard requirements.
- 0-39: Poor fit — major mismatch in core requirements.

When two candidates are both qualified, do not give them identical scores. \
Differentiate based on depth of experience, scope of projects, recency, \
and specificity of skills."""

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
    ... (3 strengths total)
  ],
  "gaps": [
    {{
      "point": "<one sentence describing a gap or weakness>",
      "resume_excerpt": "<short quote from resume, or empty string if not applicable>",
      "jd_excerpt": "<short quote from JD requirement that's missing>"
    }},
    ... (2-3 gaps total)
  ],
  "summary": "<2-3 sentence overall assessment>"
}}

Scoring guide (use the full range, do NOT cluster around 80):
- 90-100: Exceptional fit — meets all hard requirements + multiple standout strengths
- 75-89: Strong fit — meets all hard requirements with some standout areas
- 60-74: Moderate fit — meets most requirements but with real gaps
- 40-59: Weak fit — missing multiple hard requirements
- 0-39: Poor fit — major mismatch

Differentiate carefully. A candidate with 5+ years of directly relevant experience \
should score higher than one with 1-2 years, even if both technically qualify.

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
        resume_content=resume.content,
    )

def compare_multiple(
    analyses: List[ResumeAnalysis],
    jd: str,
    filenames: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    When multiple resumes are analyzed, ask the LLM to pick the best
    and explain why.

    Args:
        analyses: List of ResumeAnalysis results
        jd: Job description text
        filenames: Optional dict mapping resume_id -> filename for clearer output

    Returns:
        (best_match_id, comparison_insight) or (None, None) if only one resume.
    """
    if len(analyses) < 2:
        return None, None

    # Build candidates summary using filenames when available
    candidates_lines = []
    for a in analyses:
        display_name = (
            filenames.get(a.resume_id, a.resume_id) if filenames else a.resume_id
        )
        candidates_lines.append(
            f"- {display_name}\n"
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

    # Build a mapping hint so LLM knows which name maps to which id
    id_mapping = ""
    if filenames:
        id_mapping = "\n\nID-to-filename mapping (for your reference):\n" + "\n".join(
            f"- {rid} = {fname}" for rid, fname in filenames.items()
        )

    client = get_llm_client()
    prompt = COMPARISON_PROMPT_TEMPLATE.format(
        jd_excerpt=jd_excerpt,
        candidates_summary=candidates_summary,
    ) + id_mapping + "\n\nIMPORTANT: In the comparison_insight, refer to resumes by their filename (not by ID like 'resume_1')."

    try:
        raw = client.chat_json(prompt=prompt, temperature=0.1)
        return raw.get("best_match_id"), raw.get("comparison_insight")
    except Exception as e:
        print(f"Comparison failed, falling back to highest score: {e}")
        best = max(analyses, key=lambda a: a.overall_score)
        return best.resume_id, None

def analyze(resumes: List[ResumeInput], jd: str) -> AnalyzeResponse:
    """
    Main entry point: analyze one or more resumes against a JD.

    Returns the full structured response with JD summary.
    """
    if not resumes:
        raise ValueError("At least one resume is required")
    if not jd or not jd.strip():
        raise ValueError("JD cannot be empty")

    # Extract JD summary (do this first, fast)
    jd_summary_raw = extract_jd_summary(jd)

    # Analyze each resume
    analyses = []
    for r in resumes:
        try:
            analysis = match_single(r, jd)
            analyses.append(analysis)
        except Exception as e:
            print(f"Failed to analyze resume {r.id}: {e}")
            continue

    if not analyses:
        raise ValueError("All resume analyses failed")

    # Sort by overall score, descending
    analyses.sort(key=lambda a: a.overall_score, reverse=True)

    # Build id->filename mapping for clearer comparison output
    filenames = {r.id: r.filename for r in resumes if r.filename}

    # Multi-resume comparison
    best_match_id, comparison_insight = compare_multiple(
        analyses, jd, filenames=filenames
    )

    # Build JDSummary object (None if extraction failed)
    from .schemas import JDSummary
    jd_summary = None
    if jd_summary_raw:
        try:
            jd_summary = JDSummary(**jd_summary_raw)
        except Exception as e:
            print(f"Failed to parse JD summary: {e}")

    return AnalyzeResponse(
        results=analyses,
        best_match_id=best_match_id,
        comparison_insight=comparison_insight,
        jd_summary=jd_summary,
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


# ============================================================
# Improvement suggestion
# ============================================================

SUGGEST_SYSTEM_PROMPT = """You are an expert resume coach. \
Your job is to help job seekers improve specific weaknesses in their resume \
to better match a target job.

CRITICAL RULE — NO FABRICATION:
You may ONLY work with what the resume already says.
- You may rephrase, reframe, reorganize, or highlight existing content.
- You may NOT add new experiences, skills, projects, activities, or claims.

VERIFICATION BEFORE WRITING A REWRITTEN BULLET:
For EVERY clause in your rewritten_bullet, ask: \
"Does this exact claim appear somewhere in the original resume?"

EXAMPLES OF FABRICATION (NEVER DO THESE):
- Resume says: "Built ML models for fraud detection"
  ❌ Rewrite: "...including extensive literature review" (literature review never mentioned)
  ❌ Rewrite: "...participated in research community" (community never mentioned)
  ❌ Rewrite: "...self-study initiatives" (self-study never mentioned)
  ❌ Rewrite: "...collaborated with engineering and business teams" (collaboration never mentioned)
  ✅ Rewrite: "Developed machine learning models for fraud detection systems"

- Resume says: "Edited videos using Adobe Premiere"
  ❌ Rewrite: "...using data-driven approaches" (data-driven never mentioned)
  ✅ Rewrite: "Edited promotional videos with Adobe Premiere, managing complex \
  multi-track timelines"

WHEN TO SET REWRITTEN_BULLET TO NULL:
If the gap is a genuine missing qualification (not fixable by rewording), \
set rewritten_bullet to null and only provide honest advice in the suggestion field. \
Examples:
- Gap is "no degree in CS" and resume shows degree in Film → null. \
Advise: consider relevant coursework, online certs, or career pivot.
- Gap is "no AWS experience" and resume has zero cloud mentions → null. \
Advise: learn AWS, mention transferable skills.

OTHER RULES:
- Be concrete and actionable. Vague advice is useless.
- Keep suggestions concise (2-4 sentences max).
- If you write a rewritten_bullet, it must be ONE bullet, in resume-appropriate \
language (action verb + specific result)."""

SUGGEST_PROMPT_TEMPLATE = """A job seeker's resume has the following gap relative to a target job. \
Help them improve this aspect of their resume.

=== JOB DESCRIPTION ===
{jd}

=== RESUME ===
{resume}

=== GAP TO ADDRESS ===
Issue: {gap_point}
{jd_requirement}
{resume_context}

=== TASK ===
Provide a concrete suggestion to improve the resume for this gap.

If the candidate has related experience that could be reframed to better address this gap, \
provide a rewritten resume bullet.

If the candidate genuinely lacks this qualification, acknowledge it honestly and \
suggest realistic alternatives (e.g., highlighting transferable skills, learning resources, \
or reframing related experience).

Return a JSON object:

{{
  "suggestion": "<2-4 sentences of concrete, actionable advice>",
  "rewritten_bullet": "<a rewritten resume bullet that addresses this gap, OR null if not applicable>"
}}

Return ONLY the JSON object."""


def suggest_improvement(
    resume_content: str,
    jd: str,
    gap_point: str,
    gap_jd_excerpt: Optional[str] = None,
    gap_resume_excerpt: Optional[str] = None,
) -> dict:
    """
    Generate an improvement suggestion for a specific gap.

    Returns a dict with 'suggestion' and optionally 'rewritten_bullet'.
    """
    # Build optional context lines
    jd_req_line = f'JD requires: "{gap_jd_excerpt}"' if gap_jd_excerpt else ""
    resume_ctx_line = f'Resume currently says: "{gap_resume_excerpt}"' if gap_resume_excerpt else ""

    prompt = SUGGEST_PROMPT_TEMPLATE.format(
        jd=jd.strip(),
        resume=resume_content.strip(),
        gap_point=gap_point,
        jd_requirement=jd_req_line,
        resume_context=resume_ctx_line,
    )

    client = get_llm_client()
    raw = client.chat_json(
        prompt=prompt,
        system=SUGGEST_SYSTEM_PROMPT,
        temperature=0.2,
    )

    return {
        "suggestion": raw.get("suggestion", ""),
        "rewritten_bullet": raw.get("rewritten_bullet"),
    }


# ============================================================
# JD Summary extraction
# ============================================================

JD_SUMMARY_PROMPT_TEMPLATE = """Extract structured information from this job description.

=== JOB DESCRIPTION ===
{jd}

=== TASK ===
Return a JSON object with the following fields. Use null for any field NOT mentioned in the JD. \
Do not invent information.

{{
  "company": "<company name, or null>",
  "company_brief": "<1-2 sentence summary of what the company does, based ONLY on info in the JD; null if JD doesn't describe the company>",
  "title": "<job title, or null>",
  "location": "<city/state/country, or 'Remote', or null>",
  "employment_type": "<'Full-time' | 'Part-time' | 'Internship' | 'Contract' | null>",
  "duration": "<duration like '12 weeks' for internships, or null>",
  "salary": "<salary range if explicitly mentioned, e.g. '$165K - $190K', or null>",
  "education": "<education requirement summary, e.g. 'Bachelor's preferred', or null>",
  "key_skills": ["<top 3-5 most prominent technical skills required>"],
  "work_mode": "<'Onsite' | 'Hybrid' | 'Remote' | null>"
}}

Return ONLY the JSON object."""


def extract_jd_summary(jd: str) -> dict:
    """
    Extract structured summary from a JD using LLM.
    Returns a dict matching JDSummary schema.
    """
    client = get_llm_client()
    prompt = JD_SUMMARY_PROMPT_TEMPLATE.format(jd=jd.strip())

    try:
        raw = client.chat_json(prompt=prompt, temperature=0.1)
        return raw
    except Exception as e:
        print(f"JD summary extraction failed: {e}")
        return {}