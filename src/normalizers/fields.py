"""
Field normalization utilities.

Handles canonicalization of:
- Phone numbers → E.164 format
- Dates → YYYY-MM format
- Country names → ISO 3166 alpha-2
- Skill names → canonical lowercase form
- Emails → lowercase, trimmed
- Names → trimmed, title-cased
"""

import re
import phonenumbers
from datetime import datetime
from typing import Optional, Tuple
import pycountry


# ── Phone Normalization ──────────────────────────────────────────────

def normalize_phone(raw: str, default_region: str = "US") -> Tuple[Optional[str], float]:
    """Normalize a phone number to E.164 format.
    
    Returns (normalized_phone, confidence).
    Confidence is 1.0 if parsing is exact, 0.7 if we had to guess region.
    """
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip()
    
    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return e164, 1.0
        else:
            # Still format it even if not perfectly valid
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return e164, 0.6
    except phonenumbers.NumberParseException:
        # Try cleaning the number and re-parsing
        cleaned = re.sub(r'[^\d+]', '', raw)
        if len(cleaned) >= 7:
            try:
                parsed = phonenumbers.parse(cleaned, default_region)
                e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                return e164, 0.5
            except phonenumbers.NumberParseException:
                pass
        return raw, 0.2  # Return raw with very low confidence


def normalize_phones(phones: list, default_region: str = "US") -> Tuple[list, float]:
    """Normalize a list of phone numbers. Returns (list of E164 strings, avg confidence)."""
    if not phones:
        return [], 0.0
    
    results = []
    confidences = []
    for p in phones:
        norm, conf = normalize_phone(p, default_region)
        if norm:
            results.append(norm)
            confidences.append(conf)
    
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return results, avg_conf


# ── Date Normalization ────────────────────────────────────────────────

MONTH_MAP = {
    'jan': '01', 'january': '01',
    'feb': '02', 'february': '02',
    'mar': '03', 'march': '03',
    'apr': '04', 'april': '04',
    'may': '05',
    'jun': '06', 'june': '06',
    'jul': '07', 'july': '07',
    'aug': '08', 'august': '08',
    'sep': '09', 'september': '09',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
}


def normalize_date(raw: str) -> Tuple[Optional[str], float]:
    """Normalize a date string to YYYY-MM format.
    
    Handles: YYYY-MM, YYYY/MM, MM/YYYY, Mon YYYY, YYYY, YYYY-MM-DD, etc.
    Returns (normalized_date, confidence).
    """
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip().lower()
    
    if raw in ("present", "current", "now", "till date", "till now"):
        return "present", 1.0
    
    # Try YYYY-MM or YYYY/MM
    m = re.match(r'^(\d{4})[-/](\d{1,2})$', raw)
    if m:
        year, month = m.group(1), m.group(2).zfill(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}", 1.0
        return f"{year}-{month}", 0.5
    
    # Try YYYY-MM-DD
    m = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', raw)
    if m:
        year, month = m.group(1), m.group(2).zfill(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}", 1.0
        return f"{year}-{month}", 0.5
    
    # Try MM/YYYY or MM-YYYY
    m = re.match(r'^(\d{1,2})[-/](\d{4})$', raw)
    if m:
        month, year = m.group(1).zfill(2), m.group(2)
        if 1 <= int(month) <= 12:
            return f"{year}-{month}", 0.9
        return f"{year}-{month}", 0.5
    
    # Try "Mon YYYY" or "Month YYYY"
    m = re.match(r'^([a-z]{3,9})\s+(\d{4})$', raw)
    if m:
        month_name, year = m.group(1), m.group(2)
        if month_name in MONTH_MAP:
            return f"{year}-{MONTH_MAP[month_name]}", 0.95
    
    # Try just YYYY
    m = re.match(r'^(\d{4})$', raw)
    if m:
        return f"{m.group(1)}", 0.7  # Year only, no month
    
    # Try "MMM YYYY" with various separators
    m = re.match(r'^([a-z]{3,9})[\s,.]+(\d{4})$', raw)
    if m:
        month_name, year = m.group(1), m.group(2)
        if month_name in MONTH_MAP:
            return f"{year}-{MONTH_MAP[month_name]}", 0.9
    
    return raw, 0.2  # Can't parse, return raw with low confidence


# ── Country Normalization ────────────────────────────────────────────

def normalize_country(raw: str) -> Tuple[Optional[str], float]:
    """Normalize a country name/string to ISO 3166 alpha-2 code.
    
    Returns (alpha2_code, confidence).
    """
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip()
    
    # Already a 2-letter code?
    if len(raw) == 2 and raw.isalpha():
        upper = raw.upper()
        if pycountry.countries.get(alpha_2=upper):
            return upper, 1.0
    
    # Try lookup by name
    try:
        matches = pycountry.countries.lookup(raw)
        if matches:
            return matches.alpha_2, 1.0
    except LookupError:
        pass
    
    # Fuzzy: try case-insensitive search
    raw_lower = raw.lower()
    for country in pycountry.countries:
        if country.name.lower() == raw_lower:
            return country.alpha_2, 1.0
    
    # Partial match
    for country in pycountry.countries:
        if raw_lower in country.name.lower() or country.name.lower() in raw_lower:
            return country.alpha_2, 0.7
    
    return raw, 0.2


# ── Email Normalization ───────────────────────────────────────────────

def normalize_email(raw: str) -> Tuple[Optional[str], float]:
    """Normalize an email: lowercase, strip whitespace.
    Returns (normalized_email, confidence).
    """
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip().lower()
    
    # Basic email validation
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', raw):
        return raw, 1.0
    
    return raw, 0.5  # Suspicious format


def normalize_emails(emails: list) -> Tuple[list, float]:
    """Normalize a list of email addresses."""
    if not emails:
        return [], 0.0
    
    results = []
    confidences = []
    for e in emails:
        norm, conf = normalize_email(e)
        if norm:
            results.append(norm)
            confidences.append(conf)
    
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return results, avg_conf


# ── Name Normalization ────────────────────────────────────────────────

def normalize_name(raw: str) -> Tuple[Optional[str], float]:
    """Normalize a person's name: strip, collapse whitespace, title case.
    Returns (normalized_name, confidence).
    """
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip()
    # Collapse whitespace
    normalized = re.sub(r'\s+', ' ', raw)
    # Title case
    normalized = normalized.title()
    
    return normalized, 0.9


# ── Skill Canonicalization ───────────────────────────────────────────

# A mapping of common skill aliases to canonical form
SKILL_CANONICAL_MAP = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "golang": "go",
    "k8s": "kubernetes",
    "k8": "kubernetes",
    "aws": "amazon web services",
    "gcp": "google cloud platform",
    "azure": "microsoft azure",
    "ml": "machine learning",
    "dl": "deep learning",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "db": "database",
    "sql": "sql",
    "nosql": "nosql",
    "react.js": "react",
    "reactjs": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "angular.js": "angular",
    "angularjs": "angular",
    "node.js": "node.js",
    "nodejs": "node.js",
    "c++": "c++",
    "cpp": "c++",
    "c#": "c#",
    "csharp": "c#",
    "c sharp": "c#",
    "devops": "devops",
    "ci/cd": "ci/cd",
    "ci cd": "ci/cd",
    "continuous integration": "ci/cd",
    "rest api": "rest api",
    "restapi": "rest api",
    "restful api": "rest api",
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "mongodb": "mongodb",
    "terraform": "terraform",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "jenkins": "jenkins",
    "git": "git",
    "github": "git",
    "java": "java",
    "ruby": "ruby",
    "rails": "ruby on rails",
    "ruby on rails": "ruby on rails",
    "django": "django",
    "flask": "flask",
    "fastapi": "fastapi",
    "spring": "spring",
    "spring boot": "spring boot",
    "react": "react",
    "angular": "angular",
    "vue": "vue",
    "svelte": "svelte",
    "tailwind": "tailwind css",
    "tailwindcss": "tailwind css",
    "css": "css",
    "html": "html",
    "sass": "sass",
    "scss": "sass",
    "redux": "redux",
    "graphql": "graphql",
    "rest": "rest api",
    "microservices": "microservices",
    "agile": "agile",
    "scrum": "scrum",
    "figma": "figma",
    "spark": "apache spark",
    "apache spark": "apache spark",
    "hadoop": "apache hadoop",
    "apache hadoop": "apache hadoop",
    "pandas": "pandas",
    "numpy": "numpy",
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "tableau": "tableau",
    "power bi": "power bi",
    "powerbi": "power bi",
    "excel": "microsoft excel",
    "jira": "jira",
    "confluence": "confluence",
    "linux": "linux",
    "bash": "bash",
    "shell": "shell scripting",
    "shell scripting": "shell scripting",
}


def normalize_skill(raw: str) -> Tuple[str, float]:
    """Canonicalize a skill name to a standard form.
    Returns (canonical_skill, confidence).
    """
    if not raw or not raw.strip():
        return raw, 0.0
    
    cleaned = raw.strip().lower()
    
    if cleaned in SKILL_CANONICAL_MAP:
        return SKILL_CANONICAL_MAP[cleaned], 0.95
    
    return cleaned, 0.7


def normalize_skills(skills: list) -> Tuple[list, float]:
    """Normalize a list of skill names. Deduplicate canonical forms."""
    if not skills:
        return [], 0.0
    
    seen = set()
    results = []
    confidences = []
    
    for s in skills:
        norm, conf = normalize_skill(s)
        if norm and norm not in seen:
            seen.add(norm)
            results.append(norm)
            confidences.append(conf)
    
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return results, avg_conf


# ── Years Experience Normalization ─────────────────────────────────────

def normalize_years_experience(raw) -> Tuple[Optional[float], float]:
    """Normalize years of experience to a number.
    Handles: integers, floats, strings like "5 years", ranges like "5-7 years".
    """
    if raw is None:
        return None, 0.0
    
    if isinstance(raw, (int, float)):
        return float(raw), 1.0
    
    if isinstance(raw, str):
        raw = raw.strip().lower()
        # "5 years" or "5+ years"
        m = re.match(r'^(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)?$', raw)
        if m:
            return float(m.group(1)), 0.9
        
        # "5-7 years" → take the lower bound
        m = re.match(r'^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)?$', raw)
        if m:
            return float(m.group(1)), 0.7  # Lower confidence for ranges
    
    return None, 0.0


# ── URL Normalization ────────────────────────────────────────────────

def normalize_url(raw: str) -> Tuple[Optional[str], float]:
    """Normalize a URL: ensure scheme, strip trailing slashes."""
    if not raw or not raw.strip():
        return None, 0.0
    
    raw = raw.strip()
    
    if not raw.startswith(('http://', 'https://')):
        raw = 'https://' + raw
    
    # Basic URL validation
    if re.match(r'^https?://[a-zA-Z0-9.-]+', raw):
        return raw.rstrip('/'), 0.9
    
    return raw, 0.3
