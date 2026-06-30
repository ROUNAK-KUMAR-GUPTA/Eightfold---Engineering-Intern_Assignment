"""
Output validation utilities.

Validates that the produced output conforms to the expected schema,
whether it's the default canonical schema or a custom config-driven schema.
"""

import json
from typing import Dict, Any, List, Tuple, Optional

from src.config.projection import ProjectionConfig, validate_output


DEFAULT_SCHEMA = {
    "type": "object",
    "required": ["candidate_id"],
    "properties": {
        "candidate_id": {"type": "string"},
        "full_name": {"type": ["string", "null"]},
        "emails": {"type": ["array", "null"]},
        "phones": {"type": ["array", "null"]},
        "locations": {"type": ["array", "null"]},
        "websites": {"type": ["array", "null"]},
        "links": {"type": ["object", "null"]},
        "years_experience": {"type": ["number", "null"]},
        "summary": {"type": ["string", "null"]},
        "experience": {"type": ["array", "null"]},
        "education": {"type": ["array", "null"]},
        "provenance": {"type": "array"},
        "overall_confidence": {"type": "number"},
    },
}


def validate_default_schema(output: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate output against the default canonical profile schema.
    
    Returns (is_valid, list_of_errors).
    """
    errors = []
    
    # candidate_id is required
    if not output.get("candidate_id"):
        errors.append("Missing required field: candidate_id")
    
    # overall_confidence should be a number between 0 and 1
    conf = output.get("overall_confidence")
    if conf is not None:
        if not isinstance(conf, (int, float)):
            errors.append("overall_confidence must be a number")
        elif not (0 <= conf <= 1):
            errors.append("overall_confidence must be between 0 and 1")
    
    # provenance should be an array
    prov = output.get("provenance")
    if prov is not None and not isinstance(prov, list):
        errors.append("provenance must be an array")
    
    # Validate provenance entries
    if isinstance(prov, list):
        for i, entry in enumerate(prov):
            if not isinstance(entry, dict):
                errors.append(f"provenance[{i}] must be an object")
                continue
            if "field" not in entry:
                errors.append(f"provenance[{i}] missing 'field'")
            if "source" not in entry:
                errors.append(f"provenance[{i}] missing 'source'")
    
    # Type checks for optional fields
    type_checks = {
        "full_name": str,
        "emails": list,
        "phones": list,
        "locations": list,
        "experience": list,
        "education": list,
    }
    
    for field, expected_type in type_checks.items():
        val = output.get(field)
        if val is not None and not isinstance(val, expected_type):
            errors.append(f"{field} must be {expected_type.__name__} or null, got {type(val).__name__}")
    
    # Validate phone format (should be E.164 if present)
    phones = output.get("phones", [])
    if isinstance(phones, list):
        for i, phone in enumerate(phones):
            if isinstance(phone, str) and not phone.startswith('+'):
                # E.164 should start with +
                errors.append(f"phones[{i}] = '{phone}' is not in E.164 format (should start with +)")
    
    return len(errors) == 0, errors


def validate_custom_schema(
    output: Dict[str, Any],
    config: ProjectionConfig,
) -> Tuple[bool, List[str]]:
    """Validate output against a custom projection config schema."""
    return validate_output(output, config)


def validate_ndjsonl(file_path: str, config: Optional[ProjectionConfig] = None) -> Tuple[bool, List[str]]:
    """Validate an NDJSONL file (one JSON object per line).
    
    If config is None, validates against the default schema.
    """
    errors = []
    line_num = 0
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_num += 1
                
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                
                if config:
                    is_valid, line_errors = validate_custom_schema(obj, config)
                else:
                    is_valid, line_errors = validate_default_schema(obj)
                
                if not is_valid:
                    for err in line_errors:
                        errors.append(f"Line {line_num}: {err}")
    
    except FileNotFoundError:
        errors.append(f"File not found: {file_path}")
    
    return len(errors) == 0, errors
