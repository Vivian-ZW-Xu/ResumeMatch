"""
Core matching logic.
Uses Qwen2.5-14B with rubric-based scoring:
1. Parse JD into structured requirements + evaluation rubric.
2. For each resume, evaluate against the rubric (yes/partial/no per criterion).
3. Compute scores deterministically from rubric verdicts.
"""
from typing import List, Optional

from .llm_client import get_llm_client
from .schemas import (
    AnalyzeResponse,
    DimensionScores,
    JDRequirements,
    JDSummary,
    MatchEvidence,
    ResumeAnalysis,
    ResumeInput,
    RubricItem,
    RubricResult,
)


# ============================================================
# Prompts — JD parsing into structured requirements + rubric
# ============================================================

JD_PARSE_SYSTEM_PROMPT = """You are a strict JD parser. \
Your job is to break a job description into structured requirement categories \
and produce an evaluation rubric.

CLASSIFICATION RULES:

- HARD REQUIREMENT: a must-have qualification listed under "Requirements", \
"Qualifications", "You should possess", or similar header. \
If the JD has a bulleted list under "Requirements", EVERY item in that list is hard, \
even if individual items contain words like "preferred" or "or". \
Example: "Familiarity with cloud platforms (AWS preferred)" — the hard requirement is \
"familiarity with cloud platforms"; AWS being preferred is just a sub-preference within it. \
Example: "Experience with Django or Flask" — hard requirement is "experience with Django or Flask"; \
the candidate needs at least one of them.

- NICE-TO-HAVE: only items marked as optional AT THE TOP LEVEL. Phrases: \
"the following is a plus:", "ideal candidate would also have:", \
items prefixed with "Bonus:" or "Nice to have:".

- JOB DUTY: what the role does on the job. NOT a prerequisite. \
Phrases: "you will...", "responsibilities include...", "partner with...", "conduct...".

- NOT REQUIRED: things the JD explicitly says are NOT needed. \
Phrases: "you don't need X", "more than half come from outside X".

When in doubt between hard requirement and nice-to-have, classify as HARD requirement. \
Items in a "Requirements" list are ALWAYS hard, even with sub-clauses like "X preferred"."""


JD_PARSE_PROMPT_TEMPLATE = """Parse this job description into structured requirements.

=== JOB DESCRIPTION ===
{jd}

=== TASK ===
Return a JSON object:

{{
  "hard_requirements": [
    "<short phrase, e.g. 'Bachelor's degree in CS or related field'>",
    "<short phrase, e.g. 'Proficient in Python'>"
  ],
  "nice_to_haves": [
    "<things JD marks as preferred / plus / nice-to-have at the top level>"
  ],
  "job_duties": [
    "<things candidate WILL DO on the job, not prerequisites>"
  ],
  "not_required": [
    "<things JD explicitly says are NOT needed, e.g. 'background in finance'>"
  ],
  "evaluation_rubric": [
    {{
      "id": "r1",
      "criterion": "<single yes/no question, e.g. 'Has a degree in a technical or quantitative field?'>",
      "dimension": "<one of: skills | experience | education | industry>",
      "weight": <integer 1-10>
    }}
  ]
}}

RUBRIC RULES (most important):
- Build rubric items from HARD REQUIREMENTS. Cover EVERY hard requirement.
- THEN add 2-3 DEPTH-DIFFERENTIATION items so candidates with more substantial \
experience score higher than candidates who barely meet the minimum bar. Examples:
  - "Has 3+ years of relevant professional experience?" (experience, weight 6-7)
  - "Has experience with [JD's specific domain, e.g. quantitative finance / NLP / production ML systems]?" (experience, weight 5-7)
  - "Has demonstrated independent research output (papers, open-source projects, advanced technical depth)?" (experience, weight 5-6)
  - "Has experience at scale or in production (e.g. millions of users, sub-second latency, 100K+ requests/sec)?" (experience, weight 5-6)
- 6 to 9 rubric items total. Mix of threshold items (hard requirements) and depth items.
- Each criterion must be ATOMIC (one yes/no question, not compound).
- Each criterion must be VERIFIABLE from a resume (a recruiter can decide yes/no).
- Each depth-differentiation item must be SPECIFIC enough that a senior 5-year candidate \
with deep experience would clearly score "yes", while a fresh student with only an internship \
would score "partial" or "no".

DIMENSION MAPPING:
- skills: technical skills, languages, tools, frameworks
- experience: years, project depth, role seniority, type of work, scale, research output
- education: degree, field, level
- industry: domain alignment (only if JD demands a specific industry)

WEIGHT GUIDE:
- 9-10: absolute deal-breakers (rare)
- 6-8: hard requirements
- 4-6: depth-differentiation items
- 3-5: nice-to-have-derived items

OTHER CONSTRAINTS:
- Use simple ids: "r1", "r2", "r3"... (no brackets, no special chars).

STRICTNESS FOR "RESEARCH PROJECT WITH REAL-WORLD DATA":
If the JD requires a research project with real-world data, the rubric MUST distinguish \
real-world data analysis (e.g. "Backtested predictive factors across 10 years of equity data", \
"Analyzed 50M user records") from methodology / framework / synthetic-data projects \
(e.g. "Built generator-verifier-ranker framework on GSM8K benchmark"). \
The latter should be "partial" or "no" for this criterion, NOT "yes".

Return ONLY the JSON object."""


# ============================================================
# Prompts — Rubric-based evaluation per resume
# ============================================================

RUBRIC_EVAL_SYSTEM_PROMPT = """You are a rubric evaluator. \
For each rubric criterion, decide whether the resume meets it and cite evidence.

VERDICT RULES:
- "yes": resume contains direct, clear evidence meeting the criterion.
- "partial": resume contains related but not exact evidence \
(e.g. criterion asks for "3+ years Python", resume shows 1 year + Python projects).
- "no": resume contains no evidence relevant to this criterion.

EVIDENCE RULES:
- For "yes" or "partial", provide a SHORT direct quote from the resume.
- For "no", set evidence to empty string.
- NEVER fabricate evidence. If the resume doesn't say it, the verdict is "no".

DEPTH-VS-THRESHOLD DISTINCTION:
- Threshold criteria ("Has Python?", "Has CS degree?") only need basic evidence.
- Depth criteria ("Has 3+ years?", "Has production-scale experience?", "Has research output?") \
need SUBSTANTIAL evidence. Internships and class projects do NOT typically satisfy these — \
mark them "partial" unless the resume explicitly demonstrates the depth required.

STRICTNESS FOR "REAL-WORLD DATA" CRITERIA:
If a criterion requires a research project examining real-world data, only "yes" if the resume \
shows analysis of real-world datasets (equity data, user records, sensor data, etc.). \
Pure methodology / framework / benchmark projects (e.g. "Built generator-verifier framework on \
GSM8K") are "partial" at best, since they do not examine real-world data.

STRENGTHS AND GAPS RULES:
- Strengths: things from the resume that DIRECTLY match a hard requirement (rubric "yes").
- Gaps: hard requirements that got "no" or "partial" verdict.
- Do NOT list gaps for nice-to-haves, duties, or items the JD says are NOT required.
- Do NOT pad to fill quotas. Fewer high-quality items > more padded items."""


RUBRIC_EVAL_PROMPT_TEMPLATE = """Evaluate this resume against the rubric below.

=== JOB DESCRIPTION ===
{jd}

=== RESUME ===
{resume}

=== EVALUATION RUBRIC ===
{rubric}

=== HARD REQUIREMENTS (for context) ===
{hard_requirements}

=== NICE-TO-HAVES (NOT gaps if missing) ===
{nice_to_haves}

=== EXPLICITLY NOT REQUIRED (NEVER list as gaps) ===
{not_required}

=== TASK ===
Return a JSON object:

{{
  "rubric_results": [
    {{
      "id": "<copy id from rubric, e.g. 'r1' (no brackets)>",
      "criterion": "<copy criterion text from rubric>",
      "verdict": "yes | partial | no",
      "evidence": "<direct resume quote, or empty string>",
      "reasoning": "<one short sentence>"
    }}
  ],
  "strengths": [
    {{
      "point": "<one sentence>",
      "resume_excerpt": "<short quote from resume>",
      "jd_excerpt": "<short quote from a HARD REQUIREMENT only>"
    }}
  ],
  "gaps": [
    {{
      "point": "<one sentence>",
      "resume_excerpt": "<quote or empty string>",
      "jd_excerpt": "<short quote from a HARD REQUIREMENT only — never from duties / nice-to-haves / not-required>"
    }}
  ],
  "summary": "<2-3 sentence overall assessment>"
}}

RULES:
- rubric_results: must contain ONE entry per rubric item. Same order as input. \
Use the EXACT id from the rubric (e.g. "r1", not "[r1]").
- strengths: 1-3 items. Each must directly correspond to a "yes" rubric verdict.
- gaps: 0-3 items. Each must correspond to a "no" or "partial" verdict on a HARD REQUIREMENT. \
Returning 0 gaps is correct for strong candidates. Do NOT pad.

=== FEW-SHOT EXAMPLE ===
Suppose the JD requires "Python proficiency" + "3+ years experience" + "Bachelor's in CS",
and the resume shows "Python (5 years), MS in CS, 2 years internship at TechCorp".

Correct rubric_results would be:
- id "r1" (Has Python experience?) → verdict "yes", evidence "Python (5 years)"
- id "r2" (Has 3+ years experience?) → verdict "partial", evidence "2 years internship at TechCorp", \
reasoning "Has 2 years, slightly below 3+ requirement"
- id "r3" (Has Bachelor's in CS?) → verdict "yes", evidence "MS in CS" (MS implies BS)

Correct strengths: 1 item ("Strong Python background")
Correct gaps: 1 item ("Slightly below 3+ years experience requirement")

Return ONLY the JSON object."""


# ============================================================
# Prompts — Multi-resume comparison
# ============================================================

COMPARISON_PROMPT_TEMPLATE = """The user has uploaded multiple versions of their own resume \
and wants to know which version best fits this specific job description.

=== JOB DESCRIPTION (excerpt) ===
{jd_excerpt}

=== RESUME VERSIONS (analyzed) ===
{candidates_summary}

=== TASK ===
Recommend which version to submit, with concrete reasoning.

Return a JSON object:

{{
  "best_match_id": "<id of recommended version>",
  "comparison_insight": "<2-3 sentences explaining why this version fits THIS job better, citing specific concrete strengths (not generic phrases like 'stronger ML background'), and what makes it stronger than the others>"
}}

Return ONLY the JSON object."""


# ============================================================
# Prompts — Improvement suggestion
# ============================================================

SUGGEST_SYSTEM_PROMPT = """You are an expert resume coach. \
Your job is to help job seekers improve specific weaknesses in their resume \
to better match a target job.

CRITICAL RULE — NO FABRICATION:
You may ONLY work with what the resume already says.
- You may rephrase, reframe, reorganize, or highlight existing content.
- You may NOT add new experiences, skills, projects, activities, or claims.

VERIFICATION BEFORE WRITING A REWRITTEN BULLET:
For EVERY clause and detail in your rewritten_bullet, ask: \
"Does this exact claim appear somewhere in the original resume?"
If even ONE detail is invented, set rewritten_bullet to null instead.

WHEN TO SET REWRITTEN_BULLET TO NULL:
NULL IS THE DEFAULT. Only write a rewritten_bullet if the resume genuinely contains \
relevant material that just needs reframing. \
If you have to invent ANY detail to write the rewrite, set it to null instead.

Examples requiring null:
- Gap is "no in-depth research project" and resume shows production engineering work \
but no research projects → null. \
Do NOT invent a "social media sentiment analysis project" or any project not in the resume.
- Gap is "no degree in CS" and resume shows degree in Film → null.
- Gap is "no AWS experience" and resume has zero cloud mentions → null.
- Gap is "no leadership experience" and resume only shows individual-contributor work → null.
- Gap is "no collaboration with stakeholders" and resume only describes solo project work \
without mentioning collaboration → null. Do NOT invent "Collaborated with cross-functional teams".

EXAMPLES OF FABRICATION (NEVER DO THESE):
- Resume says: "Built ML models for fraud detection"
  ❌ Rewrite: "...including extensive literature review" (literature review never mentioned)
  ❌ Rewrite: "...collaborated with engineering and business teams" (collaboration never mentioned)
  ✅ Rewrite: "Developed machine learning models for fraud detection systems"

- Resume says: "Worked with SQL databases for data analysis on 50M+ records"
  ❌ Rewrite: "...optimizing query performance and managing schema changes" (these specifics never mentioned)
  ✅ Rewrite: "Performed data analysis on SQL databases at 50M+ record scale"

When in doubt, choose null. A null with honest advice is far better than \
a fabricated rewrite that the candidate cannot defend in an interview.

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
provide a rewritten resume bullet — BUT every detail in it must already exist in the resume.

If the candidate genuinely lacks this qualification, OR if you cannot rewrite \
without inventing details, set rewritten_bullet to null and provide honest advice in suggestion.

Return a JSON object:

{{
  "suggestion": "<2-4 sentences of concrete, actionable advice>",
  "rewritten_bullet": "<a rewritten resume bullet that uses ONLY content already in the resume, \
OR null if not applicable / would require fabrication>"
}}

Return ONLY the JSON object."""


# ============================================================
# Prompts — JD summary extraction (display card)
# ============================================================

JD_SUMMARY_SYSTEM_PROMPT = """You are an information extractor. \
Your job is to extract ONLY information that is explicitly stated in the job description. \
Do not infer, guess, or invent. If a field is not clearly mentioned, use null. \
Be literal — extract what the JD says, not what you think it might mean."""


JD_SUMMARY_PROMPT_TEMPLATE = """Extract structured information from this job description.

=== JOB DESCRIPTION ===
{jd}

=== TASK ===
Return a JSON object. Use null for any field NOT mentioned in the JD.

{{
  "company": "<company name, or null>",
  "company_brief": "<1-2 sentence summary of what the company does, based ONLY on JD content; null if JD doesn't describe the company>",
  "title": "<job title, or null>",
  "location": "<city/state/country, or 'Remote', or null>",
  "employment_type": "<'Full-time' | 'Part-time' | 'Internship' | 'Contract' | null>",
  "duration": "<duration like '12 weeks' for internships, or null>",
  "salary": "<salary range if explicitly mentioned, e.g. '$165K - $190K', or null>",
  "education": "<education requirement summary, or null>",
  "key_skills": ["<top 3-5 most prominent technical skills required>"],
  "work_mode": "<'Onsite' | 'Hybrid' | 'Remote' | null>"
}}

Return ONLY the JSON object."""


# ============================================================
# Helpers — JD parsing
# ============================================================

def extract_jd_requirements(jd: str) -> Optional[JDRequirements]:
    """
    Parse a JD into structured requirements + evaluation rubric.
    This is called ONCE per analyze() and shared across all resumes.
    """
    client = get_llm_client()
    prompt = JD_PARSE_PROMPT_TEMPLATE.format(jd=jd.strip())

    try:
        raw = client.chat_json(
            prompt=prompt,
            system=JD_PARSE_SYSTEM_PROMPT,
            temperature=0.1,
        )
        rubric_items = [RubricItem(**r) for r in raw.get("evaluation_rubric", [])]
        return JDRequirements(
            hard_requirements=raw.get("hard_requirements", []),
            nice_to_haves=raw.get("nice_to_haves", []),
            job_duties=raw.get("job_duties", []),
            not_required=raw.get("not_required", []),
            evaluation_rubric=rubric_items,
        )
    except Exception as e:
        print(f"JD requirements parsing failed: {e}")
        return None


def extract_jd_summary(jd: str) -> dict:
    """Extract structured display summary from a JD."""
    client = get_llm_client()
    prompt = JD_SUMMARY_PROMPT_TEMPLATE.format(jd=jd.strip())

    try:
        return client.chat_json(
            prompt=prompt,
            system=JD_SUMMARY_SYSTEM_PROMPT,
            temperature=0.1,
        )
    except Exception as e:
        print(f"JD summary extraction failed: {e}")
        return {}


# ============================================================
# Helpers — Score calculation (deterministic, no LLM)
# ============================================================

# verdict → numeric value
_VERDICT_VALUE = {"yes": 1.0, "partial": 0.5, "no": 0.0}

# dimension weights for overall score
_DIMENSION_WEIGHT = {
    "skills": 0.30,
    "experience": 0.35,
    "education": 0.20,
    "industry": 0.15,
}

# default score for a dimension that has no rubric items
_DEFAULT_DIM_SCORE = 75


def _calculate_scores(
    rubric_results: List[RubricResult],
    rubric: List[RubricItem],
) -> tuple[int, DimensionScores]:
    """
    Calculate dimension and overall scores from rubric verdicts.
    Returns (overall_score, DimensionScores).
    """
    rubric_lookup = {r.id: r for r in rubric}
    by_dim: dict[str, list[tuple[float, int]]] = {
        "skills": [], "experience": [], "education": [], "industry": [],
    }

    for result in rubric_results:
        item = rubric_lookup.get(result.id)
        if not item:
            continue
        value = _VERDICT_VALUE.get(result.verdict, 0.0)
        by_dim[item.dimension].append((value, item.weight))

    # Per-dimension score: weighted average mapped from [0, 1] to [40, 100].
    # Mapping floor of 40 prevents catastrophic 0s for missing dimensions
    # (e.g. industry when JD doesn't specify one).
    dim_scores = {}
    for dim, items in by_dim.items():
        if not items:
            dim_scores[dim] = _DEFAULT_DIM_SCORE
            continue
        total_weight = sum(w for _, w in items)
        weighted_sum = sum(v * w for v, w in items)
        raw = weighted_sum / total_weight if total_weight > 0 else 0.0
        dim_scores[dim] = int(40 + raw * 60)

    overall = int(sum(dim_scores[d] * w for d, w in _DIMENSION_WEIGHT.items()))

    return overall, DimensionScores(**dim_scores)


# ============================================================
# Core matching — single resume
# ============================================================

def _format_rubric_for_prompt(rubric: List[RubricItem]) -> str:
    """Format rubric items as readable text for the LLM prompt."""
    if not rubric:
        return "(No rubric — fall back to general assessment.)"
    lines = []
    for r in rubric:
        lines.append(
            f"- id={r.id} | dim={r.dimension} | weight={r.weight} | criterion: {r.criterion}"
        )
    return "\n".join(lines)


def _format_list(items: List[str]) -> str:
    """Format a string list for the LLM prompt."""
    if not items:
        return "(none)"
    return "\n".join(f"- {item}" for item in items)


def match_single(
    resume: ResumeInput,
    jd: str,
    requirements: Optional[JDRequirements],
) -> ResumeAnalysis:
    """
    Match one resume against one JD using rubric-based evaluation.
    Falls back gracefully if requirements parsing failed.
    """
    client = get_llm_client()

    # If JD parsing failed, we still need to produce SOMETHING.
    # Use empty rubric — LLM will still produce strengths/gaps/summary,
    # and dimension scores will all be the default (75).
    rubric = requirements.evaluation_rubric if requirements else []
    hard_reqs = requirements.hard_requirements if requirements else []
    nice = requirements.nice_to_haves if requirements else []
    not_req = requirements.not_required if requirements else []

    prompt = RUBRIC_EVAL_PROMPT_TEMPLATE.format(
        jd=jd.strip(),
        resume=resume.content.strip(),
        rubric=_format_rubric_for_prompt(rubric),
        hard_requirements=_format_list(hard_reqs),
        nice_to_haves=_format_list(nice),
        not_required=_format_list(not_req),
    )

    raw = client.chat_json(
        prompt=prompt,
        system=RUBRIC_EVAL_SYSTEM_PROMPT,
        temperature=0.1,
    )

    # Parse rubric results
    rubric_results = [RubricResult(**r) for r in raw.get("rubric_results", [])]

    # Compute scores deterministically
    overall_score, dim_scores = _calculate_scores(rubric_results, rubric)

    return ResumeAnalysis(
        resume_id=resume.id,
        overall_score=overall_score,
        dimension_scores=dim_scores,
        strengths=[MatchEvidence(**s) for s in raw.get("strengths", [])],
        gaps=[MatchEvidence(**g) for g in raw.get("gaps", [])],
        summary=raw.get("summary", ""),
        resume_content=resume.content,
        rubric_results=rubric_results,
    )


# ============================================================
# Core matching — multi-resume comparison
# ============================================================

def compare_multiple(
    analyses: List[ResumeAnalysis],
    jd: str,
    filenames: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Pick the best version when multiple resumes are analyzed.
    Returns (best_match_id, comparison_insight) or (None, None) if only one.
    """
    if len(analyses) < 2:
        return None, None

    candidates_lines = []
    for a in analyses:
        display_name = (
            filenames.get(a.resume_id, a.resume_id) if filenames else a.resume_id
        )
        strengths_preview = (
            "\n    ".join(f"- {s.point}" for s in a.strengths[:2])
            if a.strengths
            else "(none)"
        )
        candidates_lines.append(
            f"- {display_name}\n"
            f"  Overall: {a.overall_score}/100 "
            f"(skills={a.dimension_scores.skills}, "
            f"exp={a.dimension_scores.experience}, "
            f"edu={a.dimension_scores.education}, "
            f"industry={a.dimension_scores.industry})\n"
            f"  Summary: {a.summary}\n"
            f"  Top strengths:\n    {strengths_preview}"
        )
    candidates_summary = "\n\n".join(candidates_lines)

    jd_excerpt = jd.strip()[:800]

    id_mapping = ""
    if filenames:
        id_mapping = "\n\nID-to-filename mapping (for your reference):\n" + "\n".join(
            f"- {rid} = {fname}" for rid, fname in filenames.items()
        )

    client = get_llm_client()
    prompt = (
        COMPARISON_PROMPT_TEMPLATE.format(
            jd_excerpt=jd_excerpt,
            candidates_summary=candidates_summary,
        )
        + id_mapping
        + "\n\nIMPORTANT: In comparison_insight, refer to resumes by filename "
        "(not by ID like 'resume_1')."
    )

    try:
        raw = client.chat_json(prompt=prompt, temperature=0.1)
        return raw.get("best_match_id"), raw.get("comparison_insight")
    except Exception as e:
        print(f"Comparison failed, falling back to highest score: {e}")
        best = max(analyses, key=lambda a: a.overall_score)
        return best.resume_id, None


# ============================================================
# Improvement suggestion (F6 endpoint)
# ============================================================

def suggest_improvement(
    resume_content: str,
    jd: str,
    gap_point: str,
    gap_jd_excerpt: Optional[str] = None,
    gap_resume_excerpt: Optional[str] = None,
) -> dict:
    """Generate a concrete improvement suggestion for a specific gap."""
    jd_req_line = f'JD requires: "{gap_jd_excerpt}"' if gap_jd_excerpt else ""
    resume_ctx_line = (
        f'Resume currently says: "{gap_resume_excerpt}"' if gap_resume_excerpt else ""
    )

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
# Main entry point
# ============================================================

def analyze(resumes: List[ResumeInput], jd: str) -> AnalyzeResponse:
    """Main entry: analyze one or more resumes against a JD."""
    if not resumes:
        raise ValueError("At least one resume is required")
    if not jd or not jd.strip():
        raise ValueError("JD cannot be empty")

    # Step 1: parse JD into structured requirements + rubric (shared)
    requirements = extract_jd_requirements(jd)

    # Step 2: extract display summary (shared)
    jd_summary_raw = extract_jd_summary(jd)

    # Step 3: evaluate each resume against the rubric
    analyses = []
    for r in resumes:
        try:
            analyses.append(match_single(r, jd, requirements))
        except Exception as e:
            print(f"Failed to analyze resume {r.id}: {e}")
            continue

    if not analyses:
        raise ValueError("All resume analyses failed")

    # Sort by overall score, descending
    analyses.sort(key=lambda a: a.overall_score, reverse=True)

    # Step 4: multi-resume comparison
    filenames = {r.id: r.filename for r in resumes if r.filename}
    best_match_id, comparison_insight = compare_multiple(
        analyses, jd, filenames=filenames
    )

    # Step 5: build display summary
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
        jd_requirements=requirements,
    )


# ============================================================
# Quick test (run with: python -m backend.app.matcher)
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
    Requirements:
    - 4+ years of Python development
    - Experience with Django or Flask
    - Familiarity with cloud platforms (AWS preferred)
    - Strong knowledge of SQL databases
    - Bachelor's in CS or related field
    """

    print("Running rubric-based analysis (3 LLM calls expected)...")
    response = analyze([sample_resume], sample_jd)

    print("\n=== JD Requirements ===")
    if response.jd_requirements:
        print(f"Hard reqs: {response.jd_requirements.hard_requirements}")
        print(f"Nice-to-haves: {response.jd_requirements.nice_to_haves}")
        print(f"Rubric ({len(response.jd_requirements.evaluation_rubric)} items):")
        for r in response.jd_requirements.evaluation_rubric:
            print(f"  [{r.id}] ({r.dimension}, w={r.weight}): {r.criterion}")

    print("\n=== Results ===")
    for r in response.results:
        print(f"\nResume {r.resume_id}: {r.overall_score}/100")
        print(f"  Skills: {r.dimension_scores.skills}")
        print(f"  Experience: {r.dimension_scores.experience}")
        print(f"  Education: {r.dimension_scores.education}")
        print(f"  Industry: {r.dimension_scores.industry}")
        print(f"\nRubric verdicts:")
        for rr in r.rubric_results:
            print(f"  [{rr.id}] {rr.verdict}: {rr.criterion}")
        print(f"\nSummary: {r.summary}")