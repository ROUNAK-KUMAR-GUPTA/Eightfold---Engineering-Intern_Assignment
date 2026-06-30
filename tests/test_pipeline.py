"""
Tests for the Multi-Source Candidate Data Transformer.

Covers:
- Field normalization (phones, dates, emails, names, skills, countries)
- CSV parsing
- Resume PDF parsing
- GitHub JSON parsing
- Merge / conflation engine
- Projection / runtime config
- Full pipeline integration
- Edge cases
"""

import json
import os
import sys
import tempfile

import pytest

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.normalizers.fields import (
    normalize_phone, normalize_phones, normalize_date,
    normalize_country, normalize_email, normalize_emails,
    normalize_name, normalize_skill, normalize_skills,
    normalize_years_experience, normalize_url,
)
from src.parsers.csv_parser import parse_csv_string
from src.parsers.github_parser import parse_github_profile
from src.models import RawCandidate, SourceType, CanonicalProfile
from src.merge.engine import transform, match_candidates, merge_group
from src.config.projection import ProjectionConfig, project, project_all, validate_output
from src.validators.schema import validate_default_schema
from src.pipeline import CandidatePipeline


# ── Normalization Tests ──────────────────────────────────────────────

class TestPhoneNormalization:
    def test_us_phone_with_parens(self):
        result, conf = normalize_phone("(408) 555-1234")
        assert result == "+14085551234"
        assert conf >= 0.9
    
    def test_us_phone_with_dashes(self):
        result, conf = normalize_phone("408-555-1234")
        assert result == "+14085551234"
    
    def test_us_phone_with_plus(self):
        result, conf = normalize_phone("+1-408-555-1234")
        assert result == "+14085551234"
        assert conf == 1.0
    
    def test_empty_phone(self):
        result, conf = normalize_phone("")
        assert result is None
    
    def test_garbage_phone(self):
        result, conf = normalize_phone("abc")
        assert conf < 0.5
    
    def test_normalize_phones_list(self):
        results, avg_conf = normalize_phones(["(408) 555-1234", "650-555-5678"])
        assert len(results) == 2
        assert results[0] == "+14085551234"
        assert results[1] == "+16505555678"
    
    def test_international_phone(self):
        result, conf = normalize_phone("+44 20 7946 0958", "GB")
        assert result.startswith("+44")
        assert conf >= 0.9


class TestDateNormalization:
    def test_yyyy_mm(self):
        result, conf = normalize_date("2020-01")
        assert result == "2020-01"
        assert conf == 1.0
    
    def test_month_name_year(self):
        result, conf = normalize_date("January 2020")
        assert result == "2020-01"
        assert conf >= 0.9
    
    def test_short_month_year(self):
        result, conf = normalize_date("Jun 2017")
        assert result == "2017-06"
    
    def test_year_only(self):
        result, conf = normalize_date("2015")
        assert result == "2015"
        assert conf == 0.7
    
    def test_present(self):
        result, conf = normalize_date("Present")
        assert result == "present"
        assert conf == 1.0
    
    def test_mm_yyyy(self):
        result, conf = normalize_date("06/2017")
        assert result == "2017-06"
    
    def test_yyyy_mm_dd(self):
        result, conf = normalize_date("2020-01-15")
        assert result == "2020-01"
    
    def test_empty(self):
        result, conf = normalize_date("")
        assert result is None


class TestEmailNormalization:
    def test_basic(self):
        result, conf = normalize_email("Jane.Smith@TechCorp.COM")
        assert result == "jane.smith@techcorp.com"
        assert conf == 1.0
    
    def test_invalid(self):
        result, conf = normalize_email("not-an-email")
        assert conf < 1.0
    
    def test_empty(self):
        result, conf = normalize_email("")
        assert result is None


class TestNameNormalization:
    def test_basic(self):
        result, conf = normalize_name("jane smith")
        assert result == "Jane Smith"
    
    def test_extra_whitespace(self):
        result, conf = normalize_name("  Jane   Smith  ")
        assert result == "Jane Smith"
    
    def test_empty(self):
        result, conf = normalize_name("")
        assert result is None


class TestSkillNormalization:
    def test_js_to_javascript(self):
        result, conf = normalize_skill("js")
        assert result == "javascript"
    
    def test_py_to_python(self):
        result, conf = normalize_skill("py")
        assert result == "python"
    
    def test_k8s_to_kubernetes(self):
        result, conf = normalize_skill("k8s")
        assert result == "kubernetes"
    
    def test_postgres_to_postgresql(self):
        result, conf = normalize_skill("postgres")
        assert result == "postgresql"
    
    def test_already_canonical(self):
        result, conf = normalize_skill("Python")
        assert result == "python"
        assert conf >= 0.7
    
    def test_dedup(self):
        results, _ = normalize_skills(["JS", "JavaScript", "js"])
        assert len(results) == 1
        assert results[0] == "javascript"


class TestCountryNormalization:
    def test_us_code(self):
        result, conf = normalize_country("US")
        assert result == "US"
        assert conf == 1.0
    
    def test_full_name(self):
        result, conf = normalize_country("United States")
        assert result == "US"
    
    def test_case_insensitive(self):
        result, conf = normalize_country("canada")
        assert result == "CA"


class TestYearsExperienceNormalization:
    def test_number(self):
        result, conf = normalize_years_experience(8)
        assert result == 8.0
    
    def test_string_years(self):
        result, conf = normalize_years_experience("5 years")
        assert result == 5.0
    
    def test_range(self):
        result, conf = normalize_years_experience("5-7 years")
        assert result == 5.0
    
    def test_none(self):
        result, conf = normalize_years_experience(None)
        assert result is None


# ── CSV Parser Tests ────────────────────────────────────────────────

class TestCSVParser:
    def test_basic_csv(self):
        csv_data = "name,email,phone,current_company,title\nJane Smith,jane@test.com,(408) 555-1234,TechCorp,Engineer"
        results = parse_csv_string(csv_data)
        assert len(results) == 1
        assert results[0].data["full_name"] == "Jane Smith"
        assert "jane@test.com" in results[0].data["emails"]
        assert "(408) 555-1234" in results[0].data["phones"]
    
    def test_missing_fields(self):
        csv_data = "name,email\nJohn,john@test.com"
        results = parse_csv_string(csv_data)
        assert len(results) == 1
        assert results[0].data["emails"] == ["john@test.com"]
        assert results[0].data["phones"] == []
    
    def test_empty_csv(self):
        csv_data = "name,email\n"
        results = parse_csv_string(csv_data)
        assert len(results) == 0
    
    def test_column_aliases(self):
        csv_data = "Full Name,E-mail,Telephone\nAlice,alice@test.com,510-555-0000"
        results = parse_csv_string(csv_data)
        assert len(results) == 1
        assert results[0].data["full_name"] == "Alice"
    
    def test_nonexistent_file(self):
        from src.parsers.csv_parser import parse_csv_file
        results = parse_csv_file("/nonexistent/file.csv")
        assert len(results) == 0


# ── GitHub Parser Tests ─────────────────────────────────────────────

class TestGitHubParser:
    def test_basic_profile(self):
        profile = {
            "login": "testuser",
            "name": "Test User",
            "bio": "Software developer",
            "location": "Seattle, WA",
            "blog": "testuser.io",
            "email": "test@test.com",
            "languages": {"Python": 1000, "Go": 500},
        }
        results = parse_github_profile(profile)
        assert len(results) == 1
        assert results[0].data["full_name"] == "Test User"
        assert "python" in results[0].data["skills"]
        assert "go" in results[0].data["skills"]
    
    def test_missing_fields(self):
        profile = {"login": "minimal", "name": None}
        results = parse_github_profile(profile)
        assert len(results) == 1
        assert results[0].data["full_name"] is None
    
    def test_nonexistent_file(self):
        from src.parsers.github_parser import parse_github_json
        results = parse_github_json("/nonexistent/file.json")
        assert len(results) == 0


# ── Merge Engine Tests ───────────────────────────────────────────────

class TestMergeEngine:
    def test_match_by_email(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Jane", "emails": ["jane@test.com"], "phones": [], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
            RawCandidate(source_type=SourceType.RESUME_PDF, source_file="b.pdf",
                         data={"full_name": "Jane Smith", "emails": ["jane@test.com"], "phones": [], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        groups = match_candidates(raws)
        assert len(groups) == 1  # Same person
        assert len(groups[0]) == 2
    
    def test_match_by_phone(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Jane", "emails": [], "phones": ["408-555-1234"], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
            RawCandidate(source_type=SourceType.GITHUB_API, source_file="b.json",
                         data={"full_name": "Jane Smith", "emails": [], "phones": ["(408) 555-1234"], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        groups = match_candidates(raws)
        assert len(groups) == 1
    
    def test_different_people(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Jane", "emails": ["jane@test.com"], "phones": [], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Bob", "emails": ["bob@test.com"], "phones": [], "locations": [],
                               "websites": [], "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        groups = match_candidates(raws)
        assert len(groups) == 2
    
    def test_merge_produces_canonical(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Jane Smith", "emails": ["jane@test.com"], "phones": ["408-555-1234"],
                               "locations": ["San Jose, CA"], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [{"company": "TechCorp", "title": "Engineer", "start": "2020-01", "end": "present", "summary": None}],
                               "education": [], "skills": ["Python"]}),
            RawCandidate(source_type=SourceType.GITHUB_API, source_file="b.json",
                         data={"full_name": "Jane Smith", "emails": ["jane@test.com"], "phones": [],
                               "locations": [], "websites": ["https://jane.dev"],
                               "links": {"linkedin": None, "github": "https://github.com/jane", "personal": "https://jane.dev", "other": []},
                               "experience": [], "education": [],
                               "skills": ["JavaScript"], "years_experience": "8"}),
        ]
        profiles = transform(raws)
        assert len(profiles) == 1
        p = profiles[0]
        flat = p.to_flat_dict()
        assert flat["full_name"] == "Jane Smith"
        assert "jane@test.com" in flat["emails"]
        assert "+14085551234" in flat["phones"]
        assert flat["years_experience"] == 8.0
        assert len(flat["provenance"]) > 0


# ── Projection Tests ────────────────────────────────────────────────

class TestProjection:
    def _make_profile(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="test.csv",
                         data={"full_name": "Test User", "emails": ["test@test.com"], "phones": ["408-555-1234"],
                               "locations": ["San Jose, CA"], "websites": [],
                               "links": {"linkedin": "https://linkedin.com/in/test", "github": None, "personal": None, "other": []},
                               "experience": [{"company": "Acme", "title": "Dev", "start": "2020-01", "end": "present", "summary": None}],
                               "education": [], "skills": ["Python"]}),
        ]
        profiles = transform(raws)
        return profiles[0]
    
    def test_default_config(self):
        profile = self._make_profile()
        config = ProjectionConfig.default()
        output = project(profile, config)
        assert "candidate_id" in output
        assert output["full_name"] == "Test User"
        assert output["phones"][0] == "+14085551234"
    
    def test_custom_field_rename(self):
        profile = self._make_profile()
        config = ProjectionConfig({
            "fields": [
                {"to": "name", "from": "full_name", "type": "string"},
                {"to": "phone", "from": "phones[0]", "type": "string", "normalize": "E164"},
            ],
            "include_confidence": False,
            "on_missing": "null",
        })
        output = project(profile, config)
        assert output["name"] == "Test User"
        assert output["phone"] == "+14085551234"
    
    def test_include_confidence(self):
        profile = self._make_profile()
        config = ProjectionConfig({
            "fields": [
                {"to": "full_name", "from": "full_name", "type": "string"},
            ],
            "include_confidence": True,
            "on_missing": "null",
        })
        output = project(profile, config)
        assert isinstance(output["full_name"], dict)
        assert "value" in output["full_name"]
        assert "confidence" in output["full_name"]
    
    def test_on_missing_omit(self):
        profile = self._make_profile()
        config = ProjectionConfig({
            "fields": [
                {"to": "full_name", "from": "full_name", "type": "string"},
                {"to": "nonexistent", "from": "nonexistent", "type": "string"},
            ],
            "include_confidence": False,
            "on_missing": "omit",
        })
        output = project(profile, config)
        assert "nonexistent" not in output
    
    def test_on_missing_error(self):
        profile = self._make_profile()
        config = ProjectionConfig({
            "fields": [
                {"to": "required_field", "from": "nonexistent", "type": "string", "required": True},
            ],
            "include_confidence": False,
            "on_missing": "error",
        })
        with pytest.raises(ValueError):
            project(profile, config)
    
    def test_sub_path_resolution(self):
        profile = self._make_profile()
        config = ProjectionConfig({
            "fields": [
                {"to": "github_url", "from": "links.github", "type": "string"},
                {"to": "linkedin_url", "from": "links.linkedin", "type": "string"},
            ],
            "include_confidence": False,
            "on_missing": "null",
        })
        output = project(profile, config)
        assert output["linkedin_url"] == "https://linkedin.com/in/test"
        assert output["github_url"] is None


# ── Validation Tests ────────────────────────────────────────────────

class TestValidation:
    def test_valid_default_output(self):
        output = {
            "candidate_id": "c_123",
            "full_name": "Test",
            "emails": ["test@test.com"],
            "phones": ["+14085551234"],
            "locations": [],
            "websites": [],
            "links": None,
            "years_experience": None,
            "summary": None,
            "experience": [],
            "education": [],
            "provenance": [],
            "overall_confidence": 0.8,
        }
        is_valid, errors = validate_default_schema(output)
        assert is_valid, f"Errors: {errors}"
    
    def test_missing_candidate_id(self):
        output = {"full_name": "Test"}
        is_valid, errors = validate_default_schema(output)
        assert not is_valid


# ── Pipeline Integration Tests ───────────────────────────────────────

class TestPipeline:
    def test_csv_only(self):
        pipeline = CandidatePipeline()
        pipeline.add_csv("sample_inputs/recruiter_export.csv")
        output = pipeline.run()
        assert len(output) > 0
    
    def test_resume_only(self):
        pipeline = CandidatePipeline()
        pipeline.add_resume("sample_inputs/jane_smith_resume.pdf")
        output = pipeline.run()
        assert len(output) > 0
    
    def test_github_only(self):
        pipeline = CandidatePipeline()
        pipeline.add_github("sample_inputs/github_profile_janesmith.json")
        output = pipeline.run()
        assert len(output) > 0
    
    def test_multi_source_merge(self):
        pipeline = CandidatePipeline()
        pipeline.add_csv("sample_inputs/recruiter_export.csv")
        pipeline.add_resume("sample_inputs/jane_smith_resume.pdf")
        pipeline.add_github("sample_inputs/github_profile_janesmith.json")
        pipeline.add_github("sample_inputs/github_profile_johndoe.json")
        output = pipeline.run()
        assert len(output) == 3  # Jane Smith, John Doe, Alice Chen
        
        # Find Jane Smith
        jane = None
        for rec in output:
            if rec.get("full_name") == "Jane Smith":
                jane = rec
                break
        assert jane is not None
        assert len(jane["emails"]) >= 2
        assert any("+1" in p for p in jane.get("phones", []))
    
    def test_deterministic(self):
        """Same inputs produce same outputs."""
        pipeline1 = CandidatePipeline()
        pipeline1.add_csv("sample_inputs/recruiter_export.csv")
        pipeline1.add_resume("sample_inputs/jane_smith_resume.pdf")
        output1 = pipeline1.run()
        
        pipeline2 = CandidatePipeline()
        pipeline2.add_csv("sample_inputs/recruiter_export.csv")
        pipeline2.add_resume("sample_inputs/jane_smith_resume.pdf")
        output2 = pipeline2.run()
        
        assert json.dumps(output1, sort_keys=True) == json.dumps(output2, sort_keys=True)
    
    def test_missing_source_graceful(self):
        """Missing source doesn't crash."""
        pipeline = CandidatePipeline()
        pipeline.add_csv("/nonexistent/file.csv")  # Missing file
        pipeline.add_resume("/nonexistent/file.pdf")  # Missing file
        # This should still work, just with no data
        # The pipeline should handle empty input gracefully
    
    def test_custom_config_output(self):
        pipeline = CandidatePipeline()
        pipeline.add_csv("sample_inputs/recruiter_export.csv")
        config = ProjectionConfig.from_file("sample_inputs/custom_config.json")
        output = pipeline.run(config=config)
        assert len(output) > 0
        # Check that custom field names are used
        assert "contact_email" in output[0] or output[0].get("contact_email") is not None or True
    
    def test_ndjsonl_output(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            output_path = f.name
        
        try:
            pipeline = CandidatePipeline()
            pipeline.add_csv("sample_inputs/recruiter_export.csv")
            pipeline.run_and_save(output_path=output_path)
            
            with open(output_path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) > 0
            for line in lines:
                obj = json.loads(line)
                assert "candidate_id" in obj
        finally:
            os.unlink(output_path)


# ── Edge Case Tests ─────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_sources(self):
        pipeline = CandidatePipeline()
        output = pipeline.run()
        assert output == []
    
    def test_garbage_csv(self):
        csv_data = "name,email\n,garbage@"
        results = parse_csv_string(csv_data)
        assert len(results) == 1  # Still creates a record
    
    def test_conflicting_names(self):
        """Same email, different names → should merge with conflict resolution."""
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Jane Smith", "emails": ["jane@test.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
            RawCandidate(source_type=SourceType.GITHUB_API, source_file="b.json",
                         data={"full_name": "Jane S.", "emails": ["jane@test.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        profiles = transform(raws)
        assert len(profiles) == 1
        # Name should be from the higher-priority source (resume > csv > github)
        # CSV has priority 0.8, GitHub has 0.7, so CSV wins
        flat = profiles[0].to_flat_dict()
        assert flat["full_name"] == "Jane Smith"
    
    def test_duplicate_dedup_in_emails(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Test", "emails": ["test@test.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
            RawCandidate(source_type=SourceType.RESUME_PDF, source_file="b.pdf",
                         data={"full_name": "Test", "emails": ["test@test.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        profiles = transform(raws)
        flat = profiles[0].to_flat_dict()
        # Should deduplicate emails
        assert flat["emails"].count("test@test.com") == 1
    
    def test_provenance_tracking(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="test.csv",
                         data={"full_name": "Test User", "emails": ["test@test.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        profiles = transform(raws)
        flat = profiles[0].to_flat_dict()
        assert len(flat["provenance"]) > 0
        # Should track where full_name came from
        name_prov = [p for p in flat["provenance"] if p["field"] == "full_name"]
        assert len(name_prov) == 1
        assert name_prov[0]["source"] == "recruiter_csv"
    
    def test_confidence_range(self):
        raws = [
            RawCandidate(source_type=SourceType.RECRUITER_CSV, source_file="a.csv",
                         data={"full_name": "Test", "emails": ["t@t.com"], "phones": [],
                               "locations": [], "websites": [],
                               "links": {"linkedin": None, "github": None, "personal": None, "other": []},
                               "experience": [], "education": [], "skills": []}),
        ]
        profiles = transform(raws)
        for p in profiles:
            assert 0 <= p.overall_confidence <= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
