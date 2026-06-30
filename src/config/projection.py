"""
Runtime Config & Projection Layer.

Applies a runtime configuration to reshape the output of canonical profiles
without any code changes. This is the "projection" between the internal
canonical record and the external output format.
"""

from __future__ import annotations
import re
import json
from typing import List, Dict, Any, Optional, Tuple

from src.models import CanonicalProfile, SummaryField
from src.normalizers.fields import normalize_phone, normalize_phones, normalize_skills


class ProjectionConfig:
    """Parsed runtime configuration for output projection."""
    
    def __init__(self, config: Dict[str, Any]):
        self.fields: List[Dict[str, Any]] = config.get("fields", [])
        self.include_confidence: bool = config.get("include_confidence", False)
        self.on_missing: str = config.get("on_missing", "null")
        
        if self.on_missing not in ("null", "omit", "error"):
            raise ValueError(f"Invalid on_missing policy: {self.on_missing}")
    
    @classmethod
    def from_file(cls, path: str) -> "ProjectionConfig":
        with open(path, 'r') as f:
            config = json.load(f)
        return cls(config)
    
    @classmethod
    def from_string(cls, json_str: str) -> "ProjectionConfig":
        config = json.loads(json_str)
        return cls(config)
    
    @classmethod
    def default(cls) -> "ProjectionConfig":
        return cls({
            "fields": [
                {"to": "candidate_id", "from": "candidate_id", "type": "string", "required": True},
                {"to": "full_name", "from": "full_name", "type": "string", "required": True},
                {"to": "emails", "from": "emails", "type": "array"},
                {"to": "phones", "from": "phones", "type": "array"},
                {"to": "locations", "from": "locations", "type": "array"},
                {"to": "websites", "from": "websites", "type": "array"},
                {"to": "links", "from": "links", "type": "object"},
                {"to": "years_experience", "from": "years_experience", "type": "number"},
                {"to": "summary", "from": "summary", "type": "string"},
                {"to": "experience", "from": "experience", "type": "array"},
                {"to": "education", "from": "education", "type": "array"},
                {"to": "provenance", "from": "provenance", "type": "array"},
                {"to": "overall_confidence", "from": "overall_confidence", "type": "number"},
            ],
            "include_confidence": False,
            "on_missing": "null",
        })


def _resolve_path(data: Dict[str, Any], path: str) -> Any:
    """Resolve a dot-separated path into a nested dict.
    Supports array index: e.g., "phones[0]"
    """
    parts = re.split(r'\.', path)
    current = data
    
    for part in parts:
        m = re.match(r'^(\w+)\[(\d+)\]$', part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        else:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
    
    return current


def _unwrap_confidence(value: Any) -> Any:
    """If value is a confidence-wrapped dict, extract just the value."""
    if isinstance(value, dict) and "value" in value and "confidence" in value and "sources" in value:
        return value["value"]
    return value


def _apply_normalization(value: Any, normalize: Optional[str]) -> Any:
    if not normalize or value is None:
        return value
    
    norm = normalize.lower().strip()
    
    if norm == "e164":
        if isinstance(value, str):
            result, _ = normalize_phone(value)
            return result
        elif isinstance(value, list):
            results, _ = normalize_phones(value)
            return results
    elif norm == "canonical":
        if isinstance(value, list):
            results, _ = normalize_skills(value)
            return results
        elif isinstance(value, str):
            result, _ = normalize_skills([value])
            return result[0] if result else value
    elif norm == "lowercase":
        if isinstance(value, str):
            return value.lower()
        elif isinstance(value, list):
            return [v.lower() if isinstance(v, str) else v for v in value]
    elif norm == "uppercase":
        if isinstance(value, str):
            return value.upper()
        elif isinstance(value, list):
            return [v.upper() if isinstance(v, str) else v for v in value]
    elif norm == "trim":
        if isinstance(value, str):
            return value.strip()
        elif isinstance(value, list):
            return [v.strip() if isinstance(v, str) else v for v in value]
    
    return value


def project(profile: CanonicalProfile, config: ProjectionConfig) -> Dict[str, Any]:
    """Project a canonical profile into the configured output format.
    
    Always uses flat dict as base, then adds confidence metadata if requested.
    """
    flat = profile.to_flat_dict()
    output: Dict[str, Any] = {}
    errors: List[str] = []
    
    for field_config in config.fields:
        to_name = field_config["to"]
        from_path = field_config.get("from", to_name)
        field_type = field_config.get("type", "string")
        required = field_config.get("required", False)
        normalize = field_config.get("normalize")
        sub_path = field_config.get("path")
        
        # Resolve value from flat dict
        value = _resolve_path(flat, from_path)
        
        # If we have a sub_path and value is an object, resolve further
        if sub_path and value is not None and isinstance(value, dict):
            value = _resolve_path(value, sub_path)
        
        # Unwrap any residual confidence wrappers
        value = _unwrap_confidence(value)
        
        # If include_confidence is on, look up from confidence dict
        field_confidence = None
        field_sources = None
        if config.include_confidence:
            conf_dict = profile.to_confidence_dict()
            conf_data = _resolve_path(conf_dict, from_path)
            if isinstance(conf_data, dict) and "confidence" in conf_data:
                field_confidence = conf_data["confidence"]
                field_sources = conf_data.get("sources", [])
        
        # Handle missing values
        is_missing = (value is None) or (isinstance(value, list) and len(value) == 0)
        
        if is_missing:
            if required:
                if config.on_missing == "error":
                    errors.append(f"Required field '{to_name}' is missing")
                elif config.on_missing == "omit":
                    continue
                else:
                    output[to_name] = None
            else:
                if config.on_missing == "omit":
                    continue
                else:
                    output[to_name] = None
            continue
        
        # Apply normalization
        value = _apply_normalization(value, normalize)
        
        # Type coercion
        if field_type == "string" and not isinstance(value, str):
            value = str(value) if value is not None else None
        elif field_type == "number" and not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = None
        
        # Build output field
        if config.include_confidence and field_confidence is not None:
            output[to_name] = {
                "value": value,
                "confidence": field_confidence,
                "sources": field_sources or [],
            }
        else:
            output[to_name] = value
    
    if errors and config.on_missing == "error":
        raise ValueError(f"Projection validation errors: {'; '.join(errors)}")
    
    return output


def project_all(
    profiles: List[CanonicalProfile],
    config: ProjectionConfig,
) -> List[Dict[str, Any]]:
    """Project all profiles using the given config."""
    return [project(p, config) for p in profiles]


def validate_output(output: Dict[str, Any], config: ProjectionConfig) -> Tuple[bool, List[str]]:
    """Validate a projected output against the config schema."""
    errors = []
    
    for field_config in config.fields:
        to_name = field_config["to"]
        required = field_config.get("required", False)
        field_type = field_config.get("type")
        
        if to_name not in output:
            if required and config.on_missing != "omit":
                errors.append(f"Missing required field: {to_name}")
            continue
        
        value = output[to_name]
        
        # Unwrap confidence wrapper if present
        if isinstance(value, dict) and "value" in value and "confidence" in value:
            value = value["value"]
        
        if value is None:
            if required:
                errors.append(f"Required field is null: {to_name}")
            continue
        
        if field_type:
            type_ok = True
            if field_type == "string" and not isinstance(value, str):
                type_ok = False
            elif field_type == "number" and not isinstance(value, (int, float)):
                type_ok = False
            elif field_type == "array" and not isinstance(value, list):
                type_ok = False
            elif field_type == "object" and not isinstance(value, dict):
                type_ok = False
            
            if not type_ok:
                errors.append(f"Field '{to_name}' has wrong type: expected {field_type}, got {type(value).__name__}")
    
    return len(errors) == 0, errors
