"""
Parser for GitHub profile data (unstructured source via REST API).

In a production setting, this would call the GitHub REST API.
For this assignment, we accept a JSON file that mirrors the API response
structure, making the system testable without API keys.
"""

import json
import os
import re
from typing import List, Dict, Any, Optional
from src.models import RawCandidate, SourceType


def parse_github_json(json_path: str) -> List[RawCandidate]:
    """Parse a GitHub profile JSON file (mirrors REST API response).
    
    Expected structure (simplified):
    {
      "login": "username",
      "name": "Full Name",
      "bio": "...",
      "location": "City, Country",
      "blog": "https://example.com",
      "public_repos": 42,
      "languages": {"Python": 15000, "JavaScript": 8000},
      "repos": [
        {"name": "repo1", "description": "...", "language": "Python"}
      ]
    }
    
    Returns empty list if file is missing or parsing fails.
    """
    if not os.path.exists(json_path):
        return []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        print(f"[GitHub Parser] Warning: Could not parse {json_path}: {e}")
        return []
    
    return parse_github_profile(profile, source_file=json_path)


def parse_github_profile(profile: Dict[str, Any], source_file: str = "github_api") -> List[RawCandidate]:
    """Parse a GitHub profile dict into a RawCandidate."""
    
    data: Dict[str, Any] = {
        "full_name": profile.get("name"),
        "emails": [],
        "phones": [],
        "locations": [],
        "websites": [],
        "links": {
            "linkedin": None,
            "github": f"https://github.com/{profile.get('login', '')}",
            "personal": None,
            "other": [],
        },
        "summary": profile.get("bio"),
        "skills": [],
        "experience": [],
        "education": [],
        "years_experience": None,
    }
    
    # Location
    if profile.get("location"):
        data["locations"].append(profile["location"])
    
    # Blog/website
    if profile.get("blog"):
        blog = profile["blog"]
        if not blog.startswith("http"):
            blog = "https://" + blog
        data["websites"].append(blog)
        data["links"]["personal"] = blog
    
    # Email (GitHub may expose email)
    if profile.get("email"):
        data["emails"].append(profile["email"])
    
    # Languages → skills (canonicalized)
    from src.normalizers.fields import normalize_skills as _norm_skills
    if profile.get("languages"):
        norm_list, _ = _norm_skills(list(profile["languages"].keys()))
        data["skills"] = norm_list
    elif profile.get("repos"):
        # Derive skills from repo languages
        languages = set()
        for repo in profile.get("repos", []):
            if repo.get("language"):
                languages.add(repo["language"])
        norm_list, _ = _norm_skills(list(languages))
        data["skills"] = norm_list
    
    # Repos can hint at experience
    if profile.get("repos"):
        for repo in profile["repos"][:5]:  # Top 5 repos
            if repo.get("description"):
                # This is weak signal; we don't create experience entries
                # from repos, but we could use them for skills enrichment
                pass
    
    # Estimate years of experience from account age (weak signal)
    if profile.get("created_at"):
        # We could compute from created_at, but it's very rough
        data["years_experience"] = None  # Don't guess from GitHub
    
    candidate = RawCandidate(
        source_type=SourceType.GITHUB_API,
        source_file=source_file,
        data=data,
    )
    
    return [candidate]
