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

- HARD REQUIREMENT: a must-have qualification. Typically appears under "Requirements", \
"Qualifications", "You should possess", or a similar header — but section header alone is \
not decisive; the language of the individual item matters (see NICE-TO-HAVE rule (b)).

  Sub-clause preferences DO NOT make the whole item nice-to-have:
  Example: "Familiarity with cloud platforms (AWS preferred)" → HARD = "familiarity with cloud platforms"; \
  AWS being preferred is just a sub-preference within it.
  Example: "Experience with Django or Flask" → HARD = "experience with Django or Flask"; \
  candidate needs at least one of them.

  COMPOUND BULLETS — preserve every atomic clause:
  A single bullet may pack multiple atomic requirements joined by "and". \
SPLIT them into separate hard_requirements entries. Do NOT drop a clause.
  Example: "Knowledge of PyTorch and familiarity with DNN architectures" → \
two entries: "Knowledge of PyTorch", "Familiarity with DNN architectures".
  Example: "Bachelor's in CS and 3+ years of experience" → \
two entries: "Bachelor's in CS", "3+ years of experience".

- NICE-TO-HAVE: an item the JD marks as optional. Two patterns:
  (a) Top-level section markers: "the following is a plus:", "ideal candidate would also have:", \
  bullets prefixed with "Bonus:" or "Nice to have:".
  (b) An item — even one that appears INSIDE a Requirements list — whose ENTIRE statement is \
  qualified with optionality language. Examples: "Familiarity with Kubernetes is a plus", \
  "Experience with X preferred", "Candidates with Y are encouraged to apply", \
  "Knowledge of Z is a bonus".

  Key test: is the WHOLE item qualified, or just a sub-clause?
  - "Cloud platforms (AWS preferred)" → whole item is "cloud platforms" (HARD); only AWS is preferred.
  - "AWS experience is a plus" → the whole item is qualified (NICE-TO-HAVE).

- JOB DUTY: what the role does on the job. NOT a prerequisite. \
Phrases: "you will...", "responsibilities include...", "partner with...", "conduct...".

- NOT REQUIRED: things the JD explicitly says are NOT needed. \
Phrases: "you don't need X", "more than half come from outside X".

LITMUS TEST when uncertain between HARD and NICE-TO-HAVE:
Ask: "Would a candidate likely be filtered out at resume screening for missing this?"
- Yes / probably yes → HARD requirement.
- Maybe / would still be considered → NICE-TO-HAVE.
Do NOT default to HARD just because the item sits inside a Requirements section — read the \
item's own language first."""


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
- Build rubric items from HARD REQUIREMENTS. Cover EVERY hard requirement. \
If a hard requirement is compound (e.g. "X and Y"), split it into separate atomic items.
- MANDATORY: also add 2-4 PAST-EXPERIENCE PROXY items derived from the JD's CORE \
TECHNICAL DUTIES (see "DUTY → PAST-EXPERIENCE PROXY" below). These are the items that \
distinguish a candidate who is generically qualified from one who has actually built \
what this role does. THE RUBRIC IS INCOMPLETE WITHOUT THEM. Read the JD's \
Responsibilities / About-the-team / Intro paragraphs in full — concrete technical work \
described there must be turned into proxy items, even if not under a header literally \
named "Responsibilities".
- MANDATORY: if the JD's Preferred / Nice-to-have section names SPECIFIC TECHNOLOGIES \
or research areas (e.g. "LLM finetuning", "ModelOps", "alignment", "vector databases", \
"distributed training", named conferences, named frameworks), add 1-2 corresponding \
rubric items at LOW WEIGHT (2-3). Specific-tech mentions in Preferred are how the JD \
signals what differentiates top candidates from baseline-qualified ones — \
SKIPPING THEM defeats the purpose of the rubric.
  Skip generic nice-to-haves only when they aren't tied to a concrete technology \
(e.g. "good communication skills", "self-starter mindset" → SKIP).
- ONLY if the above don't already cover the JD's emphasis, add 1 generic DEPTH item \
(see "DEPTH ITEMS MUST REFLECT JD'S EMPHASIS" below). Do NOT add a research-flavored \
depth item just because the JD mentions "research" once — duty proxies are the primary \
signal for what the role does.
- Rubric MUST contain 7 to 9 items total. If after the steps above you have fewer than \
7, your coverage of duties or specific-tech Preferred items is too thin — go back and \
extract more proxy / nice-to-have items.
- Each criterion must be ATOMIC (one yes/no question, not compound).
- Each criterion must be VERIFIABLE from a resume (a recruiter can decide yes/no).

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

DUTY → PAST-EXPERIENCE PROXY — VERY IMPORTANT:

SCAN THE FULL JD, NOT JUST A "RESPONSIBILITIES" HEADER:
Technical duty descriptions can appear in ANY of these places — read them all:
  - Sections literally headed "Responsibilities", "What you'll do", "You will...".
  - Intro / "About the team" paragraphs ("our team builds X", "the team operates Y").
  - "About this role" prose that describes day-to-day technical work.
Do NOT skip a section just because it lacks the header "Responsibilities". \
A team-description paragraph that says "we develop and operate massively distributed \
ML training and inference systems" is a duty source.

TRANSFORMATION RULE:
For any duty whose core is a CONCRETE TECHNICAL ACTIVITY, the rubric MUST include a \
corresponding item that asks whether the candidate has PAST EXPERIENCE doing that work. \
Pattern: extract the technical noun, then ask \
"Has past experience [building / deploying / working on / optimizing] <technical noun>?"

COMPOUND DUTIES → MULTIPLE PROXY ITEMS:
A single duty sentence can pack 3-5 distinct technical activities. Each activity that \
maps to a verifiable resume artifact becomes ITS OWN rubric item. Do not roll them up.

GOOD transformations:
- Duty: "Drive the development of industry-leading recommendation systems"
  → Rubric: "Has past experience building ranking, retrieval, or recommendation systems?"
- Duty: "Own and optimize the full-stack ML pipeline—from algorithm design to system infrastructure"
  → Rubric: "Has past experience building or owning end-to-end production ML pipelines?"
- Duty: "Develop and maintain a big model as a service platform, including \
offline training/finetuning, online inference, model management, and resource orchestration"
  → Rubric (FOUR items from this one duty):
    - "Has past experience finetuning large language models (LoRA, QLoRA, full finetune)?"
    - "Has past experience deploying ML inference / model-serving systems?"
    - "Has experience with ModelOps / model lifecycle management workflows?"
    - "Has experience with compute resource orchestration (GPU scheduling, cluster mgmt)?"
- Duty (from team intro): "develop and operate massively distributed ML training and inference systems"
  → Rubric: "Has past experience working on large-scale distributed ML training or inference systems?"

DO NOT transform ABSTRACT activities into rubric items. SKIP these:
- "Collaborate with cross-functional teams" → every candidate "collaborates"; SKIP.
- "Partner with stakeholders" → too vague; SKIP.
- "Communicate findings" → SKIP unless the role's central function is communication (rare).

A duty qualifies for proxy transformation only if its core is something a candidate \
could concretely LIST on a resume — a system they built, a model they deployed, a \
pipeline they shipped, an experiment they designed.

DEPTH ITEMS MUST REFLECT JD'S EMPHASIS — VERY IMPORTANT:
Before writing depth items, identify what the JD ACTUALLY values. Read the language carefully.

JD ROLE ARCHETYPES AND THEIR DEPTH CRITERIA:

1. RESEARCH-HEAVY (quant DS, research scientist, applied scientist).
Signal phrases in JD: "develop hypotheses", "research", "literature review", \
"test theories", "communicate complex ideas", "creatively approach data analysis", \
"academic community", "rigorous", "explore". \
Depth criteria for this archetype:
  - "Has experience formulating and testing data-driven hypotheses?"
  - "Has experience translating analytical findings into recommendations or strategy?"
  - "Has experience communicating technical findings to non-technical stakeholders?"
  - "Has demonstrated independent research output (papers, deep statistical analysis)?"
  AVOID for this archetype: production scale, latency optimization, deployment pipelines — \
these are NOT what a research role values.

2. ENGINEERING-HEAVY (MLE, infra, platform engineer).
Signal phrases: "production", "latency", "scale", "deployment", "infra", \
"throughput", "distributed", "reliability". \
Depth criteria:
  - "Has experience deploying systems at production scale (millions of users / requests)?"
  - "Has experience optimizing system latency or throughput?"
  - "Has experience with model serving / production ML pipelines?"
  AVOID: hypothesis testing, stakeholder communication, literature reviews.

3. PRODUCT/ANALYTICS (data analyst, product DS).
Signal phrases: "A/B test", "dashboards", "metrics", "growth", "experimentation", \
"product decisions". \
Depth criteria:
  - "Has experience designing and analyzing A/B experiments?"
  - "Has experience building dashboards or metrics that drove business decisions?"
  - "Has experience translating data analysis into product recommendations?"

CRITICAL RULE: \
Do NOT use generic depth items like "experience with cutting-edge methodologies" or \
"experience working with large datasets" if the JD's emphasis is research-heavy — those \
are engineering-flavored and will reward the wrong type of candidate. \
Match the depth items to what the JD's signal phrases actually emphasize.

STRICTNESS FOR "RESEARCH PROJECT WITH REAL-WORLD DATA":
If the JD requires a research project with real-world data, the rubric MUST distinguish \
real-world data analysis (e.g. "Backtested predictive factors across 10 years of equity data", \
"Analyzed 50M user records") from methodology / framework / synthetic-data projects \
(e.g. "Built generator-verifier-ranker framework on GSM8K benchmark"). \
The latter should be "partial" or "no" for this criterion, NOT "yes".

Return ONLY the JSON object."""


# ============================================================
# Prompts — Rubric self-critique (post-hoc verification)
# ============================================================

RUBRIC_VERIFY_SYSTEM_PROMPT = """You are a rubric quality auditor. \
You review an evaluation rubric generated from a job description and flag rubric items \
with quality issues, so they can be removed or down-weighted before scoring resumes.

YOU MUST CHECK FOR THESE 4 ISSUE TYPES:

1. NICE_TO_HAVE_AS_HARD: The criterion measures something the JD marks as preferred / \
plus / bonus / nice-to-have (either via a top-level section like "Bonus:" or an item-level \
qualifier like "X is a plus", "Y preferred", "Z is a bonus"), AND the rubric gives it a \
weight ≥ 4 (treating it like a normal threshold check). \
If the item is already at weight ≤ 3, it is correctly down-weighted — leave it alone (keep).

2. JOB_DUTY_AS_REQUIREMENT: The criterion treats an ABSTRACT job duty — \
something like "collaboration", "communication", "partnering with stakeholders", \
"working on a team" — as a past-experience requirement. These activities are too \
generic to verify on a resume; every candidate will claim them.

   IMPORTANT EXCEPTION — KEEP technical-core proxies:
   A rubric item that asks about past experience doing the CONCRETE TECHNICAL CORE of \
a job duty is LEGITIMATE and should be KEPT. The rubric uses such proxies to measure \
whether a candidate has actually done the technical work the role requires.

   Distinguish (flag) ABSTRACT from (keep) TECHNICAL-CORE:
   - "Has experience collaborating with cross-functional teams?" → flag (abstract, every CV claims this).
   - "Has experience building recommendation / ranking / retrieval systems?" → KEEP (concrete technical core).
   - "Has experience communicating findings to stakeholders?" → flag (abstract).
   - "Has experience deploying production ML pipelines?" → KEEP (concrete).
   - "Has experience designing and analyzing A/B experiments?" → KEEP (concrete).
   - "Has experience partnering with product managers?" → flag (abstract).

   Rule: if the item names a CONCRETE TECHNICAL ARTIFACT (system, pipeline, model, \
experiment, dataset, framework) that maps to something a candidate could list on a \
resume, KEEP it. If the item names an INTERPERSONAL or PROCESS verb (collaborate, \
partner, communicate, coordinate), flag it.

3. UNREASONABLE_THRESHOLD: The criterion sets a bar inappropriate for the role level. \
Examples: requiring first-author NeurIPS/ICML/ICLR publications for an intern role; \
requiring 10+ years of experience for a new-grad position; requiring a PhD when the JD \
says "Bachelor's or Master's"; requiring open-source maintainer status for a junior role.

4. NOT_IN_JD: The criterion introduces a technical area that is NOT mentioned ANYWHERE \
in the JD body — neither in the Qualifications/Requirements section, nor in the \
Responsibilities/duties, nor in the team-intro / "About this role" paragraphs. The LLM \
hallucinated it.

   IMPORTANT — DO NOT flag duty-derived proxies as NOT_IN_JD:
   A rubric item phrased as "Has past experience [X]" where [X] is derived from a duty / \
responsibility / team-description that DOES appear in the JD body is LEGITIMATE. The \
proxy form is a transformation, not a fabrication. Example: a JD whose duties section \
says "develop the platform, including offline finetuning, online inference, model \
management" supports ALL THREE of these proxies as in-JD:
     - "Has past experience finetuning LLMs?" → KEEP (finetuning is in the duties).
     - "Has past experience deploying ML inference systems?" → KEEP (online inference is in the duties).
     - "Has experience with model lifecycle / ModelOps?" → KEEP (model management is in the duties).
   Only flag NOT_IN_JD when the rubric names a technical area with ZERO presence \
anywhere in the JD body (e.g., "Has experience with Kubernetes?" for a JD that nowhere \
mentions Kubernetes or container orchestration).

For each rubric item, return ONE of these verdicts:

- "keep": item is well-grounded in the JD and appropriate for the role level. \
This is the DEFAULT — only flag an issue if you can clearly cite which test it fails.

- "demote_to_lowweight": item has an issue but is still tangentially relevant. \
The weight will be set to a low value (2). Use this for nice-to-haves that should \
slightly differentiate strong candidates, and for borderline-unreasonable thresholds \
that still capture something useful.

- "remove": item is fundamentally flawed (NOT_IN_JD, or a JOB_DUTY incorrectly framed \
as past experience, or a clearly unreasonable threshold).

BE CONSERVATIVE: when uncertain, keep the item. Removing a valid criterion is worse \
than keeping a slightly imperfect one. Flag at most 2-3 items per rubric in most cases."""


RUBRIC_VERIFY_PROMPT_TEMPLATE = """Audit this evaluation rubric for quality issues.

=== JOB DESCRIPTION ===
{jd}

=== JD STRUCTURE (already extracted by upstream step) ===
Hard requirements:
{hard_requirements}

Nice-to-haves (items the JD marks as preferred/plus/bonus):
{nice_to_haves}

Job duties (things the candidate WILL DO on the job — NOT prerequisites):
{job_duties}

Explicitly NOT required:
{not_required}

=== RUBRIC TO AUDIT ===
{rubric}

=== TASK ===
For each rubric item above, decide whether to keep, demote, or remove it.

Return a JSON object:

{{
  "audits": [
    {{
      "id": "<rubric item id, exactly as given, e.g. 'r1'>",
      "verdict": "keep | demote_to_lowweight | remove",
      "issue_type": "NICE_TO_HAVE_AS_HARD | JOB_DUTY_AS_REQUIREMENT | UNREASONABLE_THRESHOLD | NOT_IN_JD | null",
      "reasoning": "<one short sentence citing specific JD text or rubric flaw>"
    }}
  ]
}}

RULES:
- One entry per rubric item, in the same order, with the same ids.
- If verdict is "keep", set issue_type to null.
- Reasoning must be SPECIFIC — quote or paraphrase the JD when flagging an issue.
- Default to "keep" if you cannot clearly cite which of the 4 tests the item fails.

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
    Runs a post-hoc rubric audit (LLM self-critique) before returning.
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
        hard = raw.get("hard_requirements", [])
        nice = raw.get("nice_to_haves", [])
        duties = raw.get("job_duties", [])
        not_req = raw.get("not_required", [])

        rubric_items = verify_rubric(rubric_items, jd, hard, nice, duties, not_req)

        return JDRequirements(
            hard_requirements=hard,
            nice_to_haves=nice,
            job_duties=duties,
            not_required=not_req,
            evaluation_rubric=rubric_items,
        )
    except Exception as e:
        print(f"JD requirements parsing failed: {e}")
        return None


# Weight applied when the auditor demotes a rubric item.
# Low enough to barely affect scores, high enough to still differentiate
# between candidates if everything else ties.
_DEMOTED_WEIGHT = 2


def verify_rubric(
    rubric: List[RubricItem],
    jd: str,
    hard_reqs: List[str],
    nice: List[str],
    duties: List[str],
    not_req: List[str],
) -> List[RubricItem]:
    """
    Post-hoc rubric audit. Asks the LLM to flag rubric items that:
      - reflect nice-to-haves rather than hard requirements,
      - confuse JD job duties with past-experience requirements,
      - set unreasonable thresholds for the role level,
      - introduce requirements not in the JD.

    Returns a possibly-modified rubric:
      - "keep"     → unchanged
      - "demote_to_lowweight" → weight reset to _DEMOTED_WEIGHT
      - "remove"   → dropped from the rubric

    Fail-open: if the audit call errors, returns the input rubric unchanged
    rather than blocking analysis.
    """
    if not rubric:
        return rubric

    client = get_llm_client()
    prompt = RUBRIC_VERIFY_PROMPT_TEMPLATE.format(
        jd=jd.strip(),
        hard_requirements=_format_list(hard_reqs),
        nice_to_haves=_format_list(nice),
        job_duties=_format_list(duties),
        not_required=_format_list(not_req),
        rubric=_format_rubric_for_prompt(rubric),
    )

    try:
        raw = client.chat_json(
            prompt=prompt,
            system=RUBRIC_VERIFY_SYSTEM_PROMPT,
            temperature=0.1,
        )
    except Exception as e:
        print(f"Rubric audit failed (keeping original rubric): {e}")
        return rubric

    audits = {a.get("id"): a for a in raw.get("audits", []) if a.get("id")}

    verified: List[RubricItem] = []
    for item in rubric:
        audit = audits.get(item.id)
        if not audit:
            verified.append(item)
            continue
        verdict = audit.get("verdict", "keep")
        issue = audit.get("issue_type")
        reason = audit.get("reasoning", "")
        if verdict == "remove":
            print(f"  [rubric audit] REMOVE {item.id} ({issue}): {reason}")
            continue
        if verdict == "demote_to_lowweight":
            print(
                f"  [rubric audit] DEMOTE {item.id} "
                f"(w={item.weight}→{_DEMOTED_WEIGHT}, {issue}): {reason}"
            )
            verified.append(item.model_copy(update={"weight": _DEMOTED_WEIGHT}))
            continue
        verified.append(item)

    return verified


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