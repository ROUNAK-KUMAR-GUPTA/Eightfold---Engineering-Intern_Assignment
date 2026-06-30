"""
Canonical data models for the Multi-Source Candidate Data Transformer.

Defines the internal canonical profile schema and all sub-models.
Every field tracks provenance (source + method) and confidence.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class SourceType(str, Enum):
    RECRUITER_CSV = "recruiter_csv"
    RESUME_PDF = "resume_pdf"
    GITHUB_API = "github_api"
    LINKEDIN = "linkedin"
    JOB_SITE_API = "job_site_api"
    RECRUITER_NOTES = "recruiter_notes"


class MergeMethod(str, Enum):
    DIRECT = "direct"              # Single source, no conflict
    PRIORITY_PICK = "priority_pick"  # Multiple sources, picked by priority
    MOST_RECENT = "most_recent"    # Picked most recently updated
    MANUAL_RULE = "manual_rule"    # Applied domain-specific rule
    CONCATENATED = "concatenated"  # Merged values from multiple sources
    CONFLICT_RESOLVED = "conflict_resolved"  # Conflict resolved by policy


class ProvenanceEntry(BaseModel):
    """Tracks where a field value came from and how it was derived."""
    field: str
    source: str          # e.g., "recruiter_csv", "resume_pdf"
    source_file: str = ""  # specific file/URL
    method: MergeMethod = MergeMethod.DIRECT
    raw_value: Any = None   # original value before normalization
    confidence: float = 1.0


class LinkEntry(BaseModel):
    linkedin: Optional[str] = None
    github: Optional[str] = None
    personal: Optional[str] = None
    other: List[str] = Field(default_factory=list)


class WebsiteEntry(BaseModel):
    url: str
    region: Optional[str] = None
    country: Optional[str] = None  # ISO 3166 alpha-2


class ExperienceEntry(BaseModel):
    company: str
    title: str
    start: Optional[str] = None   # YYYY-MM
    end: Optional[str] = None     # YYYY-MM or "present"
    summary: Optional[str] = None


class EducationEntry(BaseModel):
    institution: str
    degree: Optional[str] = None
    field: Optional[str] = None
    end_year: Optional[str] = None  # YYYY


class SummaryField(BaseModel):
    """A canonical field with confidence and source tracking."""
    value: Any
    confidence: float = 1.0
    sources: List[str] = Field(default_factory=list)


class CanonicalProfile(BaseModel):
    """The unified, deduplicated candidate profile."""
    candidate_id: str
    full_name: Optional[SummaryField] = None
    emails: Optional[SummaryField] = None   # List[str] wrapped
    phones: Optional[SummaryField] = None   # List[str] wrapped
    locations: Optional[SummaryField] = None  # List[str] wrapped
    websites: Optional[SummaryField] = None   # List[WebsiteEntry] wrapped
    links: Optional[SummaryField] = None      # LinkEntry wrapped
    years_experience: Optional[SummaryField] = None  # number or null
    summary: Optional[SummaryField] = None    # string
    experience: Optional[SummaryField] = None  # List[ExperienceEntry]
    education: Optional[SummaryField] = None   # List[EducationEntry]
    provenance: List[ProvenanceEntry] = Field(default_factory=list)
    overall_confidence: float = 0.0

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        """Recursively convert pydantic models and other objects to JSON-safe types."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, str)):
            return value
        if isinstance(value, dict):
            return {k: CanonicalProfile._serialize_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [CanonicalProfile._serialize_value(v) for v in value]
        # Pydantic BaseModel
        if hasattr(value, 'model_dump'):
            return value.model_dump()
        # Fallback
        return str(value)

    def to_flat_dict(self) -> Dict[str, Any]:
        """Convert to a flat dictionary suitable for JSON output.
        SummaryField values are unwrapped to their raw values,
        with confidence embedded if requested."""
        result = {"candidate_id": self.candidate_id}

        field_map = {
            "full_name": self.full_name,
            "emails": self.emails,
            "phones": self.phones,
            "locations": self.locations,
            "websites": self.websites,
            "links": self.links,
            "years_experience": self.years_experience,
            "summary": self.summary,
            "experience": self.experience,
            "education": self.education,
        }

        for name, sf in field_map.items():
            if sf is not None:
                result[name] = self._serialize_value(sf.value)
            else:
                result[name] = None

        result["provenance"] = [p.model_dump() for p in self.provenance]
        result["overall_confidence"] = self.overall_confidence
        return result

    def to_confidence_dict(self) -> Dict[str, Any]:
        """Convert to dict with confidence metadata embedded per field."""
        result = {"candidate_id": self.candidate_id}

        field_map = {
            "full_name": self.full_name,
            "emails": self.emails,
            "phones": self.phones,
            "locations": self.locations,
            "websites": self.websites,
            "links": self.links,
            "years_experience": self.years_experience,
            "summary": self.summary,
            "experience": self.experience,
            "education": self.education,
        }

        for name, sf in field_map.items():
            if sf is not None:
                result[name] = {
                    "value": self._serialize_value(sf.value),
                    "confidence": sf.confidence,
                    "sources": sf.sources,
                }
            else:
                result[name] = None

        result["provenance"] = [p.model_dump() for p in self.provenance]
        result["overall_confidence"] = self.overall_confidence
        return result


class RawCandidate(BaseModel):
    """A candidate record from a single source, pre-normalization."""
    source_type: SourceType
    source_file: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
