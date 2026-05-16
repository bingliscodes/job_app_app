from __future__ import annotations

import json

import anthropic

from jobapp.models import Job, StructuredResume, TailoredMaterial

TAILOR_SYSTEM_PROMPT = """\
You are an expert resume tailor. You will receive:
1. A candidate's resume as STRUCTURED JSON with explicit sections (skills, experience, etc.)
2. A SKILLS WHITELIST — the only skills/technologies you may reference
3. A job posting

Your task is to produce a tailored resume and cover letter using ONLY the candidate's \
existing material.

## HARD CONSTRAINTS — violations will be rejected

- **ONLY USE EXISTING SKILLS**: You may only mention skills and technologies from the \
SKILLS WHITELIST. Do not add, invent, or imply skills not on the list.
- **ONLY USE EXISTING EXPERIENCE**: Every bullet point, achievement, and responsibility \
must come from the candidate's existing experience entries. You may rephrase for clarity \
or emphasis, but the underlying fact must be present in the source.
- **ONLY USE EXISTING EDUCATION/CERTS**: Do not add degrees, institutions, or \
certifications not in the source.
- **NO FABRICATION**: Do not invent metrics, numbers, percentages, or outcomes that are \
not in the source material. If a bullet says "improved performance", do not add "by 40%".
- **PROJECTS**: Only reference projects from the source. Do not create new ones.

## What you CAN do

- Reorder sections and bullets to put the most relevant ones first
- Rephrase bullet points to better align with job description language (while keeping \
the same factual content)
- Write a professional summary that highlights relevant existing experience
- Omit irrelevant sections or bullets to keep the resume focused
- Write a cover letter that connects existing experience to job requirements
- Use keywords from the job description where they naturally match existing experience

## Output format

Respond with valid JSON:
{
  "tailored_resume_md": "Full tailored resume in Markdown",
  "cover_letter_md": "Full cover letter in Markdown",
  "key_matches": ["existing skill/experience that matches requirement X", ...],
  "suggestions": ["gaps the candidate might want to address honestly", ...],
  "skills_used": ["skill1", "skill2", ...]
}

Resume guidelines:
- Use Markdown with ## headers, bullet points, **bold**
- Include: name, contact, summary, skills (from whitelist only), experience, education
- **CRITICAL: The resume MUST fit on ONE PAGE (US Letter) when rendered.** Be aggressive
  about cutting less-relevant bullets and trimming the summary. Aim for: a 2-3 line
  summary, 3-5 bullets per experience entry (most relevant only), one line per education
  entry. Skills section should be a compact comma-separated list, not a bulleted list.
- **Contact line**: Use Markdown link syntax for any URLs the candidate has provided in
  the contact block of the structured resume (e.g. `[GitHub](https://github.com/user)`,
  `[LinkedIn](https://...)`). When `github_url` and `linkedin_url` are provided in the
  input, ALWAYS include them as Markdown links in the contact line.

Cover letter guidelines:
- Address to "Hiring Manager"
- 3-4 paragraphs connecting EXISTING experience to the role
- Professional but personable
- Do not claim skills or experience not in the source material
"""

VERIFY_SYSTEM_PROMPT = """\
You are a factual accuracy checker for tailored resumes. You will receive:
1. The ORIGINAL structured resume (source of truth)
2. The TAILORED resume and cover letter (to verify)
3. The SKILLS WHITELIST

Check for ANY of these violations:
- Skills or technologies mentioned that are NOT in the whitelist
- Experience, achievements, or metrics that are NOT in the original resume
- Fabricated numbers, percentages, or outcomes
- Companies, roles, or dates that don't match the original
- Education or certifications not in the original
- Projects not in the original

Respond with valid JSON:
{
  "passed": true/false,
  "violations": [
    {
      "type": "fabricated_skill|fabricated_experience|fabricated_metric|other",
      "detail": "What was fabricated",
      "location": "resume or cover_letter",
      "quote": "The exact fabricated text"
    }
  ]
}

If there are zero violations, return {"passed": true, "violations": []}.
Be thorough but fair — rephrasing existing content is allowed, fabricating new content is not.
"""


class TailoringEngine:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def tailor(
        self,
        resume: StructuredResume,
        job: Job,
        contact_links: dict[str, str] | None = None,
    ) -> TailoredMaterial:
        """Tailor resume with structured constraints and verification.

        contact_links: optional mapping of label → URL (e.g. {"GitHub": "https://..."})
        passed through to the prompt so they appear as hyperlinks in the contact line.
        """
        # Build skills whitelist from the structured resume
        skills_whitelist = sorted(set(resume.skills))

        # Also gather skills from project technologies
        for project in resume.projects:
            skills_whitelist.extend(project.technologies)
        skills_whitelist = sorted(set(skills_whitelist))

        # Serialize structured resume for the prompt
        resume_json = _serialize_resume(resume)

        # Pass 1: Tailor
        material = self._tailor_pass(resume_json, skills_whitelist, job, contact_links=contact_links)

        # Pass 2: Verify
        violations = self._verify_pass(resume_json, skills_whitelist, material)

        if violations:
            # Re-tailor with explicit violation feedback
            material = self._tailor_pass(
                resume_json, skills_whitelist, job,
                violation_feedback=violations,
                contact_links=contact_links,
            )

        return material

    def _tailor_pass(
        self,
        resume_json: str,
        skills_whitelist: list[str],
        job: Job,
        violation_feedback: list[dict] | None = None,
        contact_links: dict[str, str] | None = None,
    ) -> TailoredMaterial:
        contact_links_section = ""
        if contact_links:
            contact_links_section = "\n## Contact URLs (use as Markdown links in the contact line)\n\n"
            for label, url in contact_links.items():
                if url:
                    contact_links_section += f"- {label}: {url}\n"

        user_message = f"""\
## Candidate's Structured Resume

```json
{resume_json}
```

## Skills Whitelist (ONLY these may be referenced)

{json.dumps(skills_whitelist)}
{contact_links_section}
## Job Posting

**Title:** {job.title}
**Company:** {job.company}
**Location:** {job.location}

**Description:**
{job.description}
"""
        if violation_feedback:
            feedback_str = json.dumps(violation_feedback, indent=2)
            user_message += f"""

## IMPORTANT: Previous attempt had factual violations — fix them

The following violations were detected. Remove or correct ALL of them:

```json
{feedback_str}
```

Do NOT include any of the flagged content. Only use material from the original resume.
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=TAILOR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        data = _parse_json_response(response.content[0].text)

        # Post-process: strip any skills not in the whitelist from skills_used
        skills_used = data.get("skills_used", [])
        whitelist_lower = {s.lower() for s in skills_whitelist}
        verified_skills = [s for s in skills_used if s.lower() in whitelist_lower]

        return TailoredMaterial(
            job=job,
            tailored_resume_md=data["tailored_resume_md"],
            cover_letter_md=data["cover_letter_md"],
            key_matches=data.get("key_matches", []),
            suggestions=data.get("suggestions", []),
        )

    def _verify_pass(
        self,
        resume_json: str,
        skills_whitelist: list[str],
        material: TailoredMaterial,
    ) -> list[dict]:
        user_message = f"""\
## Original Structured Resume (source of truth)

```json
{resume_json}
```

## Skills Whitelist

{json.dumps(skills_whitelist)}

## Tailored Resume to Verify

{material.tailored_resume_md}

## Cover Letter to Verify

{material.cover_letter_md}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=VERIFY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        data = _parse_json_response(response.content[0].text)

        if data.get("passed", False):
            return []

        return data.get("violations", [])


def _serialize_resume(resume: StructuredResume) -> str:
    data = {
        "name": resume.name,
        "contact": resume.contact,
        "summary": resume.summary,
        "skills": resume.skills,
        "experience": [
            {
                "company": e.company,
                "title": e.title,
                "dates": e.dates,
                "bullets": e.bullets,
            }
            for e in resume.experience
        ],
        "education": [
            {
                "institution": ed.institution,
                "degree": ed.degree,
                "dates": ed.dates,
                "details": ed.details,
            }
            for ed in resume.education
        ],
        "projects": [
            {
                "name": p.name,
                "description": p.description,
                "technologies": p.technologies,
            }
            for p in resume.projects
        ],
        "certifications": resume.certifications,
    }
    return json.dumps(data, indent=2)


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text)
