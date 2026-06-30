"""
Merge / Conflation Engine.

Takes a list of RawCandidate objects (from different sources),
normalizes their fields, matches candidates across sources, merges
into a single CanonicalProfile per person, assigns confidence scores,
and tracks provenance for every field value.

Pipeline: detect → extract → normalize → match → merge → confidence → output

Match Policy:
- Primary match key: email (normalized, lowercase)
- Secondary match key: phone (E.164)
- Tertiary match key: name + location (fuzzy)

Merge Policy (priority-based):
- For scalar fields (full_name, years_experience): pick from highest-priority source
- For list fields (emails, phones, skills): union with dedup
- For structured fields (experience, education): merge and dedup
- Source priority: resume_pdf (0.9) > recruiter_csv (0.8) > github_api (0.7) > linkedin (0.7) > job_site (0.6) > notes (0.5)

Confidence Model:
- Base confidence = source priority
- Boosted if multiple sources agree (+0.1 per corroborating source, max 1.0)
- Reduced if sources conflict (-0.2 per conflicting source)
- Field-level confidence = base + adjustments
- Overall confidence = weighted average of field confidences
"""

from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from src.models import (
    RawCandidate, CanonicalProfile, SummaryField,
    ProvenanceEntry, SourceType, MergeMethod,
    ExperienceEntry, EducationEntry, LinkEntry, WebsiteEntry,
)
from src.normalizers.fields import (
    normalize_name, normalize_email, normalize_emails,
    normalize_phone, normalize_phones, normalize_date,
    normalize_country, normalize_skills, normalize_years_experience,
    normalize_url,
)


# Source priority for merge decisions (higher = more trusted)
SOURCE_PRIORITY = {
    SourceType.RESUME_PDF: 0.9,
    SourceType.RECRUITER_CSV: 0.8,
    SourceType.LINKEDIN: 0.7,
    SourceType.GITHUB_API: 0.7,
    SourceType.JOB_SITE_API: 0.6,
    SourceType.RECRUITER_NOTES: 0.5,
}


def _match_key_email(emails: List[str]) -> set:
    """Generate match keys from email addresses (normalized lowercase)."""
    keys = set()
    for e in emails:
        norm, _ = normalize_email(e)
        if norm:
            keys.add(norm)
    return keys


def _match_key_phone(phones: List[str]) -> set:
    """Generate match keys from phone numbers (E.164)."""
    keys = set()
    for p in phones:
        norm, _ = normalize_phone(p)
        if norm:
            keys.add(norm)
    return keys


def _match_key_name(name: str) -> str:
    """Generate a normalized name key for fuzzy matching."""
    norm, _ = normalize_name(name)
    if norm:
        return re.sub(r'\s+', '', norm.lower())
    return ""


def match_candidates(raws: List[RawCandidate]) -> List[List[RawCandidate]]:
    """Group raw candidates by likely identity.
    
    Uses email as primary key, phone as secondary, name+location as tertiary.
    Returns groups of RawCandidates that refer to the same person.
    """
    if not raws:
        return []
    
    # Build index: match_key → group_id
    email_to_group: Dict[str, int] = {}
    phone_to_group: Dict[str, int] = {}
    name_to_group: Dict[str, int] = {}
    groups: List[List[RawCandidate]] = []
    
    for raw in raws:
        data = raw.data
        candidate_emails = data.get("emails", [])
        candidate_phones = data.get("phones", [])
        candidate_name = data.get("full_name", "")
        
        email_keys = _match_key_email(candidate_emails)
        phone_keys = _match_key_phone(candidate_phones)
        name_key = _match_key_name(candidate_name)
        
        # Find existing group
        found_group = None
        
        for ek in email_keys:
            if ek in email_to_group:
                found_group = email_to_group[ek]
                break
        
        if found_group is None:
            for pk in phone_keys:
                if pk in phone_to_group:
                    found_group = phone_to_group[pk]
                    break
        
        if found_group is None and name_key and len(name_key) >= 5:
            if name_key in name_to_group:
                found_group = name_to_group[name_key]
        
        if found_group is not None:
            groups[found_group].append(raw)
        else:
            new_group_id = len(groups)
            groups.append([raw])
            for ek in email_keys:
                email_to_group[ek] = new_group_id
            for pk in phone_keys:
                phone_to_group[pk] = new_group_id
            if name_key and len(name_key) >= 5:
                name_to_group[name_key] = new_group_id
    
    return groups


def _merge_scalar_field(
    field_name: str,
    sources: List[Tuple[Any, RawCandidate, float]],  # (value, raw, confidence)
) -> Tuple[Any, float, List[str], ProvenanceEntry]:
    """Merge a scalar field across sources.
    
    Picks the value from the highest-priority source that has it.
    Adjusts confidence based on corroboration/conflict.
    """
    # Sort by source priority (descending)
    sources.sort(key=lambda x: SOURCE_PRIORITY.get(x[1].source_type, 0.5), reverse=True)
    
    best_value = None
    best_conf = 0.0
    best_source = ""
    best_method = MergeMethod.DIRECT
    source_list = []
    raw_values = []
    
    # Track agreement
    values_seen = set()
    for value, raw, conf in sources:
        if value is None:
            continue
        
        source_name = raw.source_type.value
        source_list.append(source_name)
        raw_values.append(str(value))
        
        str_val = str(value).lower().strip()
        
        if best_value is None:
            best_value = value
            best_conf = conf * SOURCE_PRIORITY.get(raw.source_type, 0.5)
            best_source = source_name
            best_method = MergeMethod.DIRECT
            values_seen.add(str_val)
        elif str_val in values_seen:
            # Corroborating source → boost confidence
            best_conf = min(1.0, best_conf + 0.1)
            best_method = MergeMethod.PRIORITY_PICK
        else:
            # Conflicting value → reduce confidence
            best_conf = max(0.1, best_conf - 0.2)
            best_method = MergeMethod.CONFLICT_RESOLVED
            values_seen.add(str_val)
    
    prov = ProvenanceEntry(
        field=field_name,
        source=best_source,
        source_file=sources[0][1].source_file if sources and best_value is not None else "",
        method=best_method,
        raw_value=raw_values[0] if raw_values else None,
        confidence=best_conf,
    )
    
    return best_value, best_conf, source_list, prov


def _merge_list_field(
    field_name: str,
    sources: List[Tuple[List, RawCandidate, float]],
) -> Tuple[List, float, List[str], ProvenanceEntry]:
    """Merge a list field across sources (union with dedup)."""
    seen = set()
    merged = []
    source_list = []
    confidences = []
    
    for value_list, raw, conf in sources:
        source_name = raw.source_type.value
        source_list.append(source_name)
        
        for item in value_list:
            key = str(item).lower().strip()
            if key not in seen:
                seen.add(key)
                merged.append(item)
                confidences.append(conf * SOURCE_PRIORITY.get(raw.source_type, 0.5))
    
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    
    prov = ProvenanceEntry(
        field=field_name,
        source=",".join(source_list),
        source_file=",".join(s[1].source_file for s in sources),
        method=MergeMethod.CONCATENATED,
        raw_value=None,
        confidence=avg_conf,
    )
    
    return merged, avg_conf, source_list, prov


def merge_group(group: List[RawCandidate]) -> CanonicalProfile:
    """Merge a group of RawCandidates (same person) into one CanonicalProfile.
    
    Applies normalization, then merges with provenance tracking.
    """
    # Generate a candidate ID from the first available identifier
    candidate_id = _generate_candidate_id(group)
    
    provenance_entries: List[ProvenanceEntry] = []
    
    # ── Normalize all fields first ──
    normalized_sources: List[Dict[str, Any]] = []
    
    for raw in group:
        data = raw.data
        src_priority = SOURCE_PRIORITY.get(raw.source_type, 0.5)
        
        # Normalize name
        norm_name, name_conf = normalize_name(data.get("full_name", "") or "")
        
        # Normalize emails
        norm_emails, emails_conf = normalize_emails(data.get("emails", []))
        
        # Normalize phones
        norm_phones, phones_conf = normalize_phones(data.get("phones", []))
        
        # Normalize locations (pass through for now, could add country extraction)
        locations = data.get("locations", [])
        norm_locations = [l.strip() for l in locations if l and l.strip()]
        
        # Normalize websites
        websites = data.get("websites", [])
        norm_websites = []
        for w in websites:
            norm_url, _ = normalize_url(w)
            if norm_url:
                norm_websites.append({"url": norm_url, "region": None, "country": None})
        
        # Links
        links_data = data.get("links", {})
        norm_links = {
            "linkedin": None,
            "github": None,
            "personal": None,
            "other": [],
        }
        if links_data.get("linkedin"):
            norm_url, _ = normalize_url(links_data["linkedin"])
            norm_links["linkedin"] = norm_url
        if links_data.get("github"):
            norm_url, _ = normalize_url(links_data["github"])
            norm_links["github"] = norm_url
        if links_data.get("personal"):
            norm_url, _ = normalize_url(links_data["personal"])
            norm_links["personal"] = norm_url
        norm_links["other"] = links_data.get("other", [])
        
        # Normalize experience entries
        exp_entries = data.get("experience", [])
        norm_experience = []
        for exp in exp_entries:
            start_norm, _ = normalize_date(exp.get("start", "") or "")
            end_norm, _ = normalize_date(exp.get("end", "") or "")
            norm_experience.append(ExperienceEntry(
                company=exp.get("company", "").strip() if exp.get("company") else "",
                title=exp.get("title", "").strip() if exp.get("title") else "",
                start=start_norm,
                end=end_norm,
                summary=exp.get("summary"),
            ))
        
        # Normalize education entries
        edu_entries = data.get("education", [])
        norm_education = []
        for edu in edu_entries:
            end_year_norm = None
            if edu.get("end_year"):
                end_year_norm, _ = normalize_date(str(edu["end_year"]))
            norm_education.append(EducationEntry(
                institution=edu.get("institution", "").strip() if edu.get("institution") else "",
                degree=edu.get("degree"),
                field=edu.get("field"),
                end_year=end_year_norm,
            ))
        
        # Normalize skills
        skills = data.get("skills", [])
        norm_skills, skills_conf = normalize_skills(skills)
        
        # Normalize years_experience
        yoe_raw = data.get("years_experience")
        norm_yoe, yoe_conf = normalize_years_experience(yoe_raw)
        
        # Summary
        summary = data.get("summary")
        
        normalized_sources.append({
            "raw": raw,
            "priority": src_priority,
            "full_name": (norm_name, name_conf * src_priority),
            "emails": (norm_emails, emails_conf * src_priority),
            "phones": (norm_phones, phones_conf * src_priority),
            "locations": (norm_locations, 0.8 * src_priority),
            "websites": (norm_websites, 0.8 * src_priority),
            "links": (norm_links, 0.8 * src_priority),
            "experience": (norm_experience, 0.8 * src_priority),
            "education": (norm_education, 0.8 * src_priority),
            "skills": (norm_skills, skills_conf * src_priority),
            "years_experience": (norm_yoe, yoe_conf * src_priority),
            "summary": (summary, 0.7 * src_priority),
        })
    
    # ── Merge each field ──
    
    # full_name (scalar)
    name_sources = [(ns["full_name"][0], ns["raw"], ns["full_name"][1])
                    for ns in normalized_sources if ns["full_name"][0]]
    name_val, name_conf, name_src_list, name_prov = _merge_scalar_field("full_name", name_sources)
    provenance_entries.append(name_prov)
    
    # emails (list)
    email_sources = [(ns["emails"][0], ns["raw"], ns["emails"][1])
                     for ns in normalized_sources if ns["emails"][0]]
    emails_val, emails_conf, emails_src_list, emails_prov = _merge_list_field("emails", email_sources)
    provenance_entries.append(emails_prov)
    
    # phones (list)
    phone_sources = [(ns["phones"][0], ns["raw"], ns["phones"][1])
                     for ns in normalized_sources if ns["phones"][0]]
    phones_val, phones_conf, phones_src_list, phones_prov = _merge_list_field("phones", phone_sources)
    provenance_entries.append(phones_prov)
    
    # locations (list)
    loc_sources = [(ns["locations"][0], ns["raw"], ns["locations"][1])
                   for ns in normalized_sources if ns["locations"][0]]
    locations_val, locations_conf, locations_src_list, locations_prov = _merge_list_field("locations", loc_sources)
    provenance_entries.append(locations_prov)
    
    # websites (list)
    web_sources = [(ns["websites"][0], ns["raw"], ns["websites"][1])
                   for ns in normalized_sources if ns["websites"][0]]
    websites_val, websites_conf, websites_src_list, websites_prov = _merge_list_field("websites", web_sources)
    provenance_entries.append(websites_prov)
    
    # links (scalar-ish, but complex object)
    link_sources = [(ns["links"][0], ns["raw"], ns["links"][1])
                    for ns in normalized_sources]
    # Merge links by picking best value for each sub-field
    merged_link = LinkEntry()
    link_conf = 0.0
    link_sources_list = []
    for link_data, raw, conf in link_sources:
        link_sources_list.append(raw.source_type.value)
        if link_data.get("linkedin") and not merged_link.linkedin:
            merged_link.linkedin = link_data["linkedin"]
            link_conf = max(link_conf, conf)
        if link_data.get("github") and not merged_link.github:
            merged_link.github = link_data["github"]
            link_conf = max(link_conf, conf)
        if link_data.get("personal") and not merged_link.personal:
            merged_link.personal = link_data["personal"]
            link_conf = max(link_conf, conf)
        for other in link_data.get("other", []):
            if other not in merged_link.other:
                merged_link.other.append(other)
    links_prov = ProvenanceEntry(
        field="links",
        source=",".join(link_sources_list),
        source_file=",".join(s[1].source_file for s in link_sources),
        method=MergeMethod.CONCATENATED,
        raw_value=None,
        confidence=link_conf,
    )
    provenance_entries.append(links_prov)
    
    # experience (list merge with dedup)
    all_experience = []
    exp_source_list = []
    exp_confidences = []
    seen_exp = set()
    for ns in normalized_sources:
        exp_list = ns["experience"][0]
        if exp_list:
            exp_source_list.append(ns["raw"].source_type.value)
            for exp in exp_list:
                key = f"{exp.company}|{exp.title}|{exp.start}"
                if key not in seen_exp:
                    seen_exp.add(key)
                    all_experience.append(exp)
                    exp_confidences.append(ns["experience"][1])
    exp_conf = sum(exp_confidences) / len(exp_confidences) if exp_confidences else 0.0
    exp_prov = ProvenanceEntry(
        field="experience",
        source=",".join(exp_source_list),
        source_file=",".join(ns["raw"].source_file for ns in normalized_sources if ns["experience"][0]),
        method=MergeMethod.CONCATENATED,
        raw_value=None,
        confidence=exp_conf,
    )
    provenance_entries.append(exp_prov)
    
    # education (list merge with dedup)
    all_education = []
    edu_source_list = []
    edu_confidences = []
    seen_edu = set()
    for ns in normalized_sources:
        edu_list = ns["education"][0]
        if edu_list:
            edu_source_list.append(ns["raw"].source_type.value)
            for edu in edu_list:
                key = f"{edu.institution}|{edu.degree}|{edu.end_year}"
                if key not in seen_edu:
                    seen_edu.add(key)
                    all_education.append(edu)
                    edu_confidences.append(ns["education"][1])
    edu_conf = sum(edu_confidences) / len(edu_confidences) if edu_confidences else 0.0
    edu_prov = ProvenanceEntry(
        field="education",
        source=",".join(edu_source_list),
        source_file=",".join(ns["raw"].source_file for ns in normalized_sources if ns["education"][0]),
        method=MergeMethod.CONCATENATED,
        raw_value=None,
        confidence=edu_conf,
    )
    provenance_entries.append(edu_prov)
    
    # years_experience (scalar)
    yoe_sources = [(ns["years_experience"][0], ns["raw"], ns["years_experience"][1])
                   for ns in normalized_sources if ns["years_experience"][0] is not None]
    yoe_val, yoe_conf, yoe_src_list, yoe_prov = _merge_scalar_field("years_experience", yoe_sources)
    provenance_entries.append(yoe_prov)
    
    # summary (scalar)
    summary_sources = [(ns["summary"][0], ns["raw"], ns["summary"][1])
                       for ns in normalized_sources if ns["summary"][0]]
    summary_val, summary_conf, summary_src_list, summary_prov = _merge_scalar_field("summary", summary_sources)
    provenance_entries.append(summary_prov)
    
    # ── Compute overall confidence ──
    field_confidences = [
        name_conf, emails_conf, phones_conf, locations_conf,
        websites_conf, link_conf, exp_conf, edu_conf,
        yoe_conf, summary_conf,
    ]
    # Weight by importance: name and email matter most
    weights = [0.25, 0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.05, 0.05, 0.1]
    total_weight = sum(w for c, w in zip(field_confidences, weights) if c > 0)
    overall_conf = (
        sum(c * w for c, w in zip(field_confidences, weights) if c > 0) / total_weight
        if total_weight > 0 else 0.0
    )
    
    # ── Assemble canonical profile ──
    profile = CanonicalProfile(
        candidate_id=candidate_id,
        full_name=SummaryField(value=name_val, confidence=name_conf, sources=name_src_list) if name_val else None,
        emails=SummaryField(value=emails_val, confidence=emails_conf, sources=emails_src_list) if emails_val else None,
        phones=SummaryField(value=phones_val, confidence=phones_conf, sources=phones_src_list) if phones_val else None,
        locations=SummaryField(value=locations_val, confidence=locations_conf, sources=locations_src_list) if locations_val else None,
        websites=SummaryField(
            value=[WebsiteEntry(**w) for w in websites_val],
            confidence=websites_conf,
            sources=websites_src_list
        ) if websites_val else None,
        links=SummaryField(value=merged_link, confidence=link_conf, sources=link_sources_list) if merged_link else None,
        years_experience=SummaryField(value=yoe_val, confidence=yoe_conf, sources=yoe_src_list) if yoe_val is not None else None,
        summary=SummaryField(value=summary_val, confidence=summary_conf, sources=summary_src_list) if summary_val else None,
        experience=SummaryField(
            value=[e.model_dump() for e in all_experience],
            confidence=exp_conf,
            sources=exp_source_list
        ) if all_experience else None,
        education=SummaryField(
            value=[e.model_dump() for e in all_education],
            confidence=edu_conf,
            sources=edu_source_list
        ) if all_education else None,
        provenance=provenance_entries,
        overall_confidence=round(overall_conf, 3),
    )
    
    return profile


def _generate_candidate_id(group: List[RawCandidate]) -> str:
    """Generate a deterministic candidate ID from the group.
    
    Uses the first available email (normalized) as the basis.
    Falls back to phone, then name hash.
    """
    import hashlib
    
    # Try email
    for raw in group:
        for email in raw.data.get("emails", []):
            norm, _ = normalize_email(email)
            if norm:
                return "c_" + hashlib.md5(norm.encode()).hexdigest()[:12]
    
    # Try phone
    for raw in group:
        for phone in raw.data.get("phones", []):
            norm, _ = normalize_phone(phone)
            if norm:
                return "c_" + hashlib.md5(norm.encode()).hexdigest()[:12]
    
    # Try name
    for raw in group:
        name = raw.data.get("full_name", "")
        if name:
            norm, _ = normalize_name(name)
            if norm:
                return "c_" + hashlib.md5(norm.lower().encode()).hexdigest()[:12]
    
    return "c_unknown_" + hashlib.md5(str(id(group)).encode()).hexdigest()[:8]


def transform(raws: List[RawCandidate]) -> List[CanonicalProfile]:
    """Full pipeline: match → normalize → merge → confidence.
    
    Takes all raw candidates from all sources and produces
    one CanonicalProfile per unique person.
    """
    groups = match_candidates(raws)
    profiles = [merge_group(g) for g in groups]
    return profiles
