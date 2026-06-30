"""
Parser for Resume PDF files (unstructured source).

Extracts text from PDF using pdftotext, then uses regex-based
extraction to identify key fields.
"""

import os
import re
import subprocess
from typing import List, Dict, Any, Optional
from src.models import RawCandidate, SourceType


# US state abbreviations for location validation
US_STATES = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC'
}

# Known countries for validation
KNOWN_COUNTRIES = {
    'usa', 'united states', 'canada', 'uk', 'united kingdom', 'india',
    'germany', 'france', 'australia', 'japan', 'china', 'brazil',
    'mexico', 'italy', 'spain', 'netherlands', 'sweden', 'norway',
    'singapore', 'south korea', 'israel', 'ireland', 'switzerland',
}


def extract_text_from_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        return ""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout
    except Exception as e:
        print(f"[Resume Parser] Warning: Could not extract text from {pdf_path}: {e}")
        return ""


def extract_email(text: str) -> List[str]:
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))


def extract_phones(text: str) -> List[str]:
    patterns = [
        r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\+\d{1,3}[-.\s]\d{2,4}[-.\s]\d{6,8}',
    ]
    phones = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        phones.extend(matches)
    return list(set(phones))


def extract_linkedin(text: str) -> Optional[str]:
    pattern = r'(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None


def extract_github(text: str) -> Optional[str]:
    pattern = r'(?:https?://)?(?:www\.)?github\.com/[a-zA-Z0-9_-]+/?'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None


def extract_websites(text: str) -> List[str]:
    pattern = r'https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[/\w.-]*'
    urls = re.findall(pattern, text)
    return [u for u in urls if 'linkedin.com' not in u and 'github.com' not in u]


def extract_name(text: str) -> Optional[str]:
    lines = text.strip().split('\n')
    skip_words = {'resume', 'curriculum', 'vitae', 'cv', 'profile', 'contact'}
    section_headers = {'experience', 'education', 'skills', 'summary', 'objective',
                       'projects', 'certifications', 'awards', 'publications',
                       'references', 'interests', 'languages', 'volunteer'}
    for line in lines[:15]:
        line = line.strip()
        if not line:
            continue
        if any(w in line.lower() for w in skip_words):
            continue
        if any(w in line.lower() for w in section_headers):
            continue
        words = line.split()
        if 1 <= len(words) <= 5:
            alpha_ratio = sum(1 for w in words if re.match(r'^[A-Za-z.-]+$', w)) / len(words)
            if alpha_ratio >= 0.6 and not line.endswith(':'):
                return line
    return None


def extract_skills_section(text: str) -> List[str]:
    skills = []
    pattern = r'(?:Skills|Technical Skills|Core Competencies|Technologies|Tools & Technologies)\s*[:\n]\s*(.*?)(?=\n\n|\n[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\s*\n|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        skills_text = match.group(1)
        if '|' in skills_text:
            skills = [s.strip() for s in skills_text.split('|') if s.strip()]
        elif '\u2022' in skills_text:
            skills = [s.strip() for s in skills_text.split('\u2022') if s.strip()]
        elif '\n' in skills_text and len(skills_text.split('\n')) > 2:
            skills = [s.strip().lstrip('\u2022-\\u2013* ') for s in skills_text.split('\n') if s.strip()]
        else:
            skills = [s.strip() for s in re.split(r'[,;]', skills_text) if s.strip()]
    return skills


def extract_experience_section(text: str) -> List[Dict[str, Any]]:
    experiences = []
    pattern = r'(?:Experience|Work Experience|Professional Experience|Employment)\s*[:\n]\s*(.*?)(?=\n(?:Education|Skills|Projects|Certifications|Awards|Summary|Objective|References|Languages)\s*[\n:]|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return experiences
    exp_text = match.group(1)
    
    # Date pattern with en-dash/em-dash support
    date_pattern = r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*(?:[-\u2013\u2014\u2012]|to)+\s*(?:Present|Current|Now|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}))'
    
    entries = re.split(r'\n\n+', exp_text)
    for entry in entries:
        if not entry.strip():
            continue
        exp = {"company": "", "title": "", "start": None, "end": None, "summary": None}
        
        date_match = re.search(date_pattern, entry, re.IGNORECASE)
        if date_match:
            date_range = date_match.group(1)
            parts = re.split(r'\s*(?:[-\u2013\u2014\u2012]|to)+\s*', date_range, maxsplit=1)
            if parts:
                exp["start"] = parts[0].strip()
            if len(parts) > 1:
                exp["end"] = parts[1].strip()
        
        lines = [l.strip() for l in entry.split('\n') if l.strip()]
        if lines:
            first = lines[0]
            at_match = re.match(r'(.+?)\s+at\s+(.+)', first, re.IGNORECASE)
            if at_match:
                exp["title"] = at_match.group(1).strip()
                exp["company"] = at_match.group(2).strip()
            else:
                exp["title"] = first
            
            if len(lines) > 1 and not exp["company"]:
                # Second line might be company or date
                second = lines[1]
                if not re.search(date_pattern, second, re.IGNORECASE):
                    exp["company"] = second
            
            summary_lines = []
            for l in lines[2:]:
                if not re.search(date_pattern, l, re.IGNORECASE):
                    summary_lines.append(l)
            if summary_lines:
                exp["summary"] = " ".join(summary_lines)
        
        if exp["company"] or exp["title"]:
            experiences.append(exp)
    return experiences


def extract_education_section(text: str) -> List[Dict[str, Any]]:
    educations = []
    pattern = r'(?:Education|Academic Background|Qualifications)\s*[:\n]\s*(.*?)(?=\n(?:Experience|Skills|Projects|Certifications|Awards|Summary|Objective|References|Languages|Volunteer|Interests)\s*[\n:]|\Z)'
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return educations
    edu_text = match.group(1)
    entries = re.split(r'\n\n+', edu_text)
    for entry in entries:
        if not entry.strip():
            continue
        edu = {"institution": "", "degree": None, "field": None, "end_year": None}
        lines = [l.strip() for l in entry.split('\n') if l.strip()]
        if lines:
            first = lines[0]
            year_match = re.search(r'(19|20)\d{2}', first)
            if year_match:
                edu["end_year"] = year_match.group(0)
            degree_keywords = ['bachelor', 'master', 'phd', 'ph.d', 'b.s', 'm.s',
                             'b.a', 'm.a', 'b.tech', 'm.tech', 'mba', 'b.e', 'm.e',
                             'doctorate', 'associate', 'diploma', 'certificate']
            first_lower = first.lower()
            is_degree_line = any(kw in first_lower for kw in degree_keywords)
            if is_degree_line:
                in_match = re.match(r'(.+?)\s+in\s+(.+)', first, re.IGNORECASE)
                if in_match:
                    edu["degree"] = in_match.group(1).strip()
                    edu["field"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', in_match.group(2)).strip()
                else:
                    edu["degree"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', first).strip()
                if len(lines) > 1:
                    edu["institution"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', lines[1]).strip()
                    year_match2 = re.search(r'(19|20)\d{2}', lines[1])
                    if year_match2:
                        edu["end_year"] = year_match2.group(0)
            else:
                edu["institution"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', first).strip()
                if len(lines) > 1:
                    second = lines[1]
                    year_match2 = re.search(r'(19|20)\d{2}', second)
                    if year_match2:
                        edu["end_year"] = year_match2.group(0)
                    in_match = re.match(r'(.+?)\s+in\s+(.+)', second, re.IGNORECASE)
                    if in_match:
                        edu["degree"] = in_match.group(1).strip()
                        edu["field"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', in_match.group(2)).strip()
                    else:
                        edu["degree"] = re.sub(r'\s*,?\s*(19|20)\d{2}\s*$', '', second).strip()
        if edu["institution"] or edu["degree"]:
            educations.append(edu)
    return educations


def extract_years_experience(text: str) -> Optional[str]:
    patterns = [
        r'(\d+)\+?\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)',
        r'(?:experience|exp)(?:\s*:\s*)(\d+)\+?\s*years?',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_location(text: str) -> List[str]:
    """Extract location from resume text.
    Only returns valid "City, ST" or "City, Country" patterns.
    Filters out false positives from skills/technical text.
    """
    locations = []
    
    # Look in the top section (first ~5 non-empty lines) for contact info with location
    lines = text.strip().split('\n')
    contact_section = []
    for line in lines[:10]:
        line = line.strip()
        if line:
            contact_section.append(line)
    
    contact_text = '\n'.join(contact_section)
    
    # "City, ST" format (e.g., "San Jose, CA") - only from contact section
    pattern1 = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2})\b'
    for m in re.finditer(pattern1, contact_text):
        candidate = m.group(1)
        parts = candidate.split(', ')
        if len(parts) == 2 and parts[1] in US_STATES:
            locations.append(candidate)
    
    # "City, Country" - only from contact section  
    pattern2 = r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*))'
    for m in re.finditer(pattern2, contact_text):
        candidate = m.group(1)
        country_part = m.group(2).strip().lower()
        if country_part in KNOWN_COUNTRIES:
            locations.append(candidate)
    
    return list(set(locations))


def parse_resume_pdf(pdf_path: str) -> List[RawCandidate]:
    text = extract_text_from_pdf(pdf_path)
    if not text or not text.strip():
        return []
    data: Dict[str, Any] = {
        "full_name": extract_name(text),
        "emails": extract_email(text),
        "phones": extract_phones(text),
        "locations": extract_location(text),
        "websites": extract_websites(text),
        "links": {
            "linkedin": extract_linkedin(text),
            "github": extract_github(text),
            "personal": None,
            "other": [],
        },
        "summary": None,
        "skills": extract_skills_section(text),
        "experience": extract_experience_section(text),
        "education": extract_education_section(text),
        "years_experience": extract_years_experience(text),
    }
    candidate = RawCandidate(
        source_type=SourceType.RESUME_PDF,
        source_file=pdf_path,
        data=data,
    )
    return [candidate]
