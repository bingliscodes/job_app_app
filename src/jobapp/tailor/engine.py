from __future__ import annotations

import json

import anthropic

from jobapp.models import Job, ParsedResume, TailoredMaterial

SYSTEM_PROMPT = """\
You are an expert career coach and resume writer. Your job is to tailor a candidate's \
resume and write a cover letter for a specific job posting.

You will receive:
1. The candidate's current resume text
2. A job posting with title, company, and description

Your task:
1. Analyze the job requirements and identify key skills, technologies, and qualifications.
2. Rewrite the resume to emphasize relevant experience, skills, and achievements that \
match the job. Keep all information truthful — rephrase and reorder, but never fabricate \
experience or skills the candidate doesn't have.
3. Write a compelling cover letter (3-4 paragraphs) that connects the candidate's \
experience to the specific role and company.
4. List the key matches between the resume and job requirements.
5. List suggestions for things the candidate might want to manually adjust or add.

Respond with valid JSON in this exact format:
{
  "tailored_resume_md": "Full tailored resume in Markdown format",
  "cover_letter_md": "Full cover letter in Markdown format",
  "key_matches": ["match 1", "match 2", ...],
  "suggestions": ["suggestion 1", "suggestion 2", ...]
}

Guidelines for the resume:
- Use clean Markdown with headers (##), bullet points, and bold for emphasis
- Lead with a professional summary tailored to this specific role
- Reorder sections and bullets to put the most relevant experience first
- Use keywords from the job description naturally
- Keep it concise (aim for 1-2 pages when rendered)

Guidelines for the cover letter:
- Address it to "Hiring Manager" unless a specific name is given
- Opening paragraph: express enthusiasm for the specific role and company
- Middle paragraphs: connect 2-3 key experiences to job requirements
- Closing: call to action, express eagerness to discuss further
- Professional but personable tone
"""


class TailoringEngine:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def tailor(self, resume: ParsedResume, job: Job) -> TailoredMaterial:
        user_message = f"""\
## Candidate's Resume

{resume.raw_text}

---

## Job Posting

**Title:** {job.title}
**Company:** {job.company}
**Location:** {job.location}

**Description:**
{job.description}
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text

        # Parse JSON response — handle cases where Claude wraps in ```json
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]  # Remove opening ```json
            text = text.rsplit("```", 1)[0]  # Remove closing ```

        data = json.loads(text)

        return TailoredMaterial(
            job=job,
            tailored_resume_md=data["tailored_resume_md"],
            cover_letter_md=data["cover_letter_md"],
            key_matches=data.get("key_matches", []),
            suggestions=data.get("suggestions", []),
        )
