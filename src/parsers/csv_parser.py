"""
Parser for Recruiter CSV export (structured source).

Expected columns: name, email, phone, current_company, title
But we handle various column names flexibly.
"""

import csv
import re
from typing import List, Dict, Any, Optional
from src.models import RawCandidate, SourceType


# Column name aliases (lowercase) → canonical field
COLUMN_MAP = {
    "name": "full_name",
    "full_name": "full_name",
    "fullname": "full_name",
    "candidate_name": "full_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "emails": "emails",
    "e-mail": "email",
    "phone": "phone",
    "phones": "phones",
    "telephone": "phone",
    "mobile": "phone",
    "cell": "phone",
    "current_company": "current_company",
    "company": "current_company",
    "employer": "current_company",
    "organization": "current_company",
    "title": "title",
    "job_title": "title",
    "role": "title",
    "position": "title",
    "location": "location",
    "city": "location",
    "address": "location",
    "linkedin": "linkedin",
    "linkedin_url": "linkedin",
    "github": "github",
    "github_url": "github",
    "website": "website",
    "portfolio": "website",
    "summary": "summary",
    "bio": "summary",
    "skills": "skills",
    "education": "education",
    "years_experience": "years_experience",
    "experience": "years_experience",
    "yoe": "years_experience",
}


def parse_csv_file(file_path: str) -> List[RawCandidate]:
    """Parse a recruiter CSV export into a list of RawCandidate objects.
    
    Handles flexible column naming and missing fields gracefully.
    """
    candidates = []
    
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            if reader.fieldnames is None:
                return candidates
            
            # Map columns to canonical names
            col_mapping = {}
            for col in reader.fieldnames:
                normalized_col = col.strip().lower().replace(' ', '_')
                if normalized_col in COLUMN_MAP:
                    col_mapping[col] = COLUMN_MAP[normalized_col]
                else:
                    col_mapping[col] = normalized_col
            
            for row_idx, row in enumerate(reader):
                data: Dict[str, Any] = {
                    "emails": [],
                    "phones": [],
                    "locations": [],
                    "websites": [],
                    "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                    "experience": [],
                    "education": [],
                    "skills": [],
                }
                
                for orig_col, canonical in col_mapping.items():
                    val = row.get(orig_col, "").strip() if row.get(orig_col) else ""
                    if not val:
                        continue
                    
                    if canonical == "full_name":
                        data["full_name"] = val
                    elif canonical in ("first_name", "last_name"):
                        existing = data.get("full_name", "")
                        if canonical == "first_name":
                            data["full_name"] = val + (" " + existing.split(" ", 1)[-1] if existing else "")
                        else:
                            first = existing.split(" ", 1)[0] if existing else ""
                            data["full_name"] = (first + " " + val).strip()
                    elif canonical == "email":
                        data["emails"].append(val)
                    elif canonical == "emails":
                        data["emails"].extend([e.strip() for e in val.split(",") if e.strip()])
                    elif canonical == "phone":
                        data["phones"].append(val)
                    elif canonical == "phones":
                        data["phones"].extend([p.strip() for p in val.split(",") if p.strip()])
                    elif canonical == "location":
                        data["locations"].append(val)
                    elif canonical == "current_company":
                        data["current_company"] = val
                    elif canonical == "title":
                        data["current_title"] = val
                    elif canonical == "linkedin":
                        data["links"]["linkedin"] = val
                    elif canonical == "github":
                        data["links"]["github"] = val
                    elif canonical == "website":
                        data["websites"].append(val)
                    elif canonical == "summary":
                        data["summary"] = val
                    elif canonical == "skills":
                        data["skills"].extend([s.strip() for s in re.split(r'[,;|]', val) if s.strip()])
                    elif canonical == "years_experience":
                        data["years_experience"] = val
                    else:
                        data[canonical] = val
                
                # Build experience entry from current_company/title if present
                if data.get("current_company") or data.get("current_title"):
                    data["experience"].append({
                        "company": data.get("current_company", ""),
                        "title": data.get("current_title", ""),
                        "start": None,
                        "end": "present",
                        "summary": None,
                    })
                
                # Clean up temporary keys
                data.pop("current_company", None)
                data.pop("current_title", None)
                
                candidate = RawCandidate(
                    source_type=SourceType.RECRUITER_CSV,
                    source_file=file_path,
                    data=data,
                )
                candidates.append(candidate)
    
    except FileNotFoundError:
        pass  # Missing source = graceful degradation
    except Exception as e:
        # Log but don't crash
        print(f"[CSV Parser] Warning: Error parsing {file_path}: {e}")
    
    return candidates


def parse_csv_string(csv_content: str, source_name: str = "inline_csv") -> List[RawCandidate]:
    """Parse CSV content from a string instead of a file."""
    import io
    
    candidates = []
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        
        if reader.fieldnames is None:
            return candidates
        
        col_mapping = {}
        for col in reader.fieldnames:
            normalized_col = col.strip().lower().replace(' ', '_')
            if normalized_col in COLUMN_MAP:
                col_mapping[col] = COLUMN_MAP[normalized_col]
            else:
                col_mapping[col] = normalized_col
        
        for row_idx, row in enumerate(reader):
            data: Dict[str, Any] = {
                "emails": [],
                "phones": [],
                "locations": [],
                "websites": [],
                "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                "experience": [],
                "education": [],
                "skills": [],
            }
            
            for orig_col, canonical in col_mapping.items():
                val = row.get(orig_col, "").strip() if row.get(orig_col) else ""
                if not val:
                    continue
                
                if canonical == "full_name":
                    data["full_name"] = val
                elif canonical in ("first_name", "last_name"):
                    existing = data.get("full_name", "")
                    if canonical == "first_name":
                        data["full_name"] = val + (" " + existing.split(" ", 1)[-1] if existing else "")
                    else:
                        first = existing.split(" ", 1)[0] if existing else ""
                        data["full_name"] = (first + " " + val).strip()
                elif canonical == "email":
                    data["emails"].append(val)
                elif canonical == "emails":
                    data["emails"].extend([e.strip() for e in val.split(",") if e.strip()])
                elif canonical == "phone":
                    data["phones"].append(val)
                elif canonical == "phones":
                    data["phones"].extend([p.strip() for p in val.split(",") if p.strip()])
                elif canonical == "location":
                    data["locations"].append(val)
                elif canonical == "current_company":
                    data["current_company"] = val
                elif canonical == "title":
                    data["current_title"] = val
                elif canonical == "linkedin":
                    data["links"]["linkedin"] = val
                elif canonical == "github":
                    data["links"]["github"] = val
                elif canonical == "website":
                    data["websites"].append(val)
                elif canonical == "summary":
                    data["summary"] = val
                elif canonical == "skills":
                    data["skills"].extend([s.strip() for s in re.split(r'[,;|]', val) if s.strip()])
                elif canonical == "years_experience":
                    data["years_experience"] = val
                else:
                    data[canonical] = val
            
            if data.get("current_company") or data.get("current_title"):
                data["experience"].append({
                    "company": data.get("current_company", ""),
                    "title": data.get("current_title", ""),
                    "start": None,
                    "end": "present",
                    "summary": None,
                })
            
            data.pop("current_company", None)
            data.pop("current_title", None)
            
            candidate = RawCandidate(
                source_type=SourceType.RECRUITER_CSV,
                source_file=source_name,
                data=data,
            )
            candidates.append(candidate)
    
    except Exception as e:
        print(f"[CSV Parser] Warning: Error parsing inline CSV: {e}")
    
    return candidates
