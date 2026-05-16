from __future__ import annotations

import re

# Companies whose career sites consistently require account creation /
# sign-in before submitting an application. Matched case-insensitively as
# substrings against the job's company name. Conservative list — we'd rather
# let a few slip through than block legitimate direct-apply jobs.
DEFAULT_ACCOUNT_REQUIRED = frozenset({
    # Big tech / FAANG-adjacent
    "apple",
    "microsoft",
    "google",
    "alphabet",
    "meta",
    "facebook",
    "amazon",
    "netflix",
    "nvidia",
    "tesla",
    "spacex",
    # Other large employers with proprietary login-walled ATS
    "oracle",
    "ibm",
    "dell",
    "hp ",
    "hewlett packard",
    "intel",
    "cisco",
    "salesforce",
    "adobe",
    "vmware",
    "sap",
    "uber",
    "lyft",
    "linkedin",
    "twitter",
    "x corp",
    # Big banks / finance
    "jpmorgan",
    "j.p. morgan",
    "goldman sachs",
    "morgan stanley",
    "bank of america",
    "wells fargo",
    "citigroup",
    "citibank",
    "capital one",
    # Retail/consumer with Workday/etc.
    "walmart",
    "target",
    "costco",
    "home depot",
    "lowe's",
    "starbucks",
    # Telcos and big infra
    "at&t",
    "verizon",
    "t-mobile",
    "comcast",
    # Healthcare / pharma with strict ATS
    "unitedhealth",
    "cvs health",
    "kaiser permanente",
    "anthem",
    "humana",
    # Big airlines / hospitality
    "delta air",
    "united airlines",
    "american airlines",
    "marriott",
    "hilton",
})


def company_requires_account(company: str, blocklist: frozenset[str] | None = None) -> bool:
    """Return True if the company name matches a known login-walled employer.

    Match is case-insensitive substring on word boundaries (so "Apple" matches
    "Apple Inc" but not "Pineapple Inc"). The blocklist defaults to
    DEFAULT_ACCOUNT_REQUIRED; pass a custom set to extend or replace.
    """
    if not company:
        return False
    blocklist = blocklist if blocklist is not None else DEFAULT_ACCOUNT_REQUIRED
    company_lower = company.lower()
    for pattern in blocklist:
        pat = pattern.lower().strip()
        if not pat:
            continue
        # If the pattern already contains non-word chars (e.g. "j.p. morgan",
        # "at&t"), do a plain substring match. Otherwise word-boundary match.
        if re.search(r"\W", pat):
            if pat in company_lower:
                return True
        else:
            if re.search(rf"\b{re.escape(pat)}\b", company_lower):
                return True
    return False
