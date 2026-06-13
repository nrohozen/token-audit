"""Test suite for token_audit.scanner module."""

import pytest
from pathlib import Path

from token_audit.scanner import scan_directory, scan_file


class TestScanFile:
    """Tests for scan_file function."""

    def test_scan_file_returns_records_and_skipped_count(self):
        """scan_file returns a tuple of (list[TokenRecord], int)."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, skipped = scan_file(fixture_path, "project-alpha")
        assert isinstance(records, list)
        assert isinstance(skipped, int)

    def test_scan_file_session_001_counts(self):
        """session-001 has 3 assistant messages and 1 malformed line."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, skipped = scan_file(fixture_path, "project-alpha")
        assert len(records) == 3
        assert skipped == 1

    def test_scan_file_session_001_message_one(self):
        """First message in session-001 has correct token counts."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        r = records[0]
        assert r.input_tokens == 1000
        assert r.output_tokens == 200
        assert r.cache_creation_tokens == 500
        assert r.cache_read_tokens == 800
        assert r.model == "claude-sonnet-4-6"

    def test_scan_file_session_001_message_two(self):
        """Second message in session-001 has correct token counts."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        r = records[1]
        assert r.input_tokens == 2000
        assert r.output_tokens == 400
        assert r.cache_creation_tokens == 1000
        assert r.cache_read_tokens == 1600

    def test_scan_file_session_001_message_three(self):
        """Third message in session-001 has correct token counts."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        r = records[2]
        assert r.input_tokens == 1500
        assert r.output_tokens == 300
        assert r.cache_creation_tokens == 750
        assert r.cache_read_tokens == 1200

    def test_scan_file_session_002_haiku_messages(self):
        """session-002 has haiku messages with zero cache creation."""
        fixture_path = Path("tests/fixtures/project-alpha/session-002.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        assert len(records) == 3
        r1, r2, r3 = records
        assert r1.model == "claude-haiku-4-5-20251001"
        assert r1.input_tokens == 500
        assert r1.output_tokens == 100
        assert r1.cache_creation_tokens == 0
        assert r1.cache_read_tokens == 400
        assert r2.input_tokens == 800
        assert r2.output_tokens == 150
        assert r2.cache_creation_tokens == 0
        assert r2.cache_read_tokens == 600

    def test_scan_file_session_002_third_message_zero_tokens(self):
        """Third message in session-002 is all zeros."""
        fixture_path = Path("tests/fixtures/project-alpha/session-002.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        r = records[2]
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.cache_creation_tokens == 0
        assert r.cache_read_tokens == 0
        assert r.model == "claude-sonnet-4-6"

    def test_scan_file_sets_project_name(self):
        """Scanned records have the correct project name set."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        assert all(r.project == "project-alpha" for r in records)

    def test_scan_file_sets_session_file_name(self):
        """Scanned records have the session file name set."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        assert all(r.session_file == "session-001.jsonl" for r in records)

    def test_scan_file_sets_model(self):
        """All scanned records have a model field."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        assert all(r.model for r in records)

    def test_scan_file_sets_timestamp(self):
        """All scanned records have a timestamp."""
        fixture_path = Path("tests/fixtures/project-alpha/session-001.jsonl")
        records, _ = scan_file(fixture_path, "project-alpha")
        assert all(r.timestamp is not None for r in records)

    def test_scan_file_missing_cache_fields_treated_as_zero(self):
        """session-004 msg 1 lacks cache fields; scanner treats them as 0."""
        fixture_path = Path("tests/fixtures/project-beta/session-004.jsonl")
        records, _ = scan_file(fixture_path, "project-beta")
        # First record has no cache fields in JSON
        r = records[0]
        assert r.input_tokens == 3000
        assert r.output_tokens == 500
        assert r.cache_creation_tokens == 0
        assert r.cache_read_tokens == 0

    def test_scan_file_nonexistent_file(self):
        """Scanning a nonexistent file returns empty records and skipped=1."""
        fixture_path = Path("tests/fixtures/nonexistent.jsonl")
        records, skipped = scan_file(fixture_path, "test-project")
        assert records == []
        assert skipped == 1

    def test_scan_file_filters_non_assistant_messages(self):
        """Scan file skips non-assistant messages (e.g., user messages)."""
        fixture_path = Path("tests/fixtures/empty-project/session-empty.jsonl")
        records, _ = scan_file(fixture_path, "empty-project")
        assert len(records) == 0


class TestScanDirectory:
    """Tests for scan_directory function."""

    def test_scan_directory_returns_scan_result(self):
        """scan_directory returns a ScanResult object."""
        from token_audit.models import ScanResult
        result = scan_directory(Path("tests/fixtures"))
        assert isinstance(result, ScanResult)
        assert isinstance(result.records, list)
        assert isinstance(result.skipped_lines, int)
        assert isinstance(result.scanned_files, int)

    def test_scan_directory_total_records(self):
        """Scanning all fixtures yields 12 records total."""
        result = scan_directory(Path("tests/fixtures"))
        assert len(result.records) == 12

    def test_scan_directory_skipped_lines(self):
        """Scanning all fixtures skips 1 malformed line."""
        result = scan_directory(Path("tests/fixtures"))
        assert result.skipped_lines == 1

    def test_scan_directory_scanned_files(self):
        """Scanning all fixtures scans exactly 5 files."""
        result = scan_directory(Path("tests/fixtures"))
        assert result.scanned_files == 5

    def test_scan_directory_project_alpha_records(self):
        """project-alpha has 6 records (3 from each session file)."""
        result = scan_directory(Path("tests/fixtures"))
        alpha_records = [r for r in result.records if r.project == "project-alpha"]
        assert len(alpha_records) == 6

    def test_scan_directory_project_beta_records(self):
        """project-beta has 6 records (4 from session-003, 2 from session-004)."""
        result = scan_directory(Path("tests/fixtures"))
        beta_records = [r for r in result.records if r.project == "project-beta"]
        assert len(beta_records) == 6

    def test_scan_directory_empty_project_no_records(self):
        """empty-project has no records (only user messages)."""
        result = scan_directory(Path("tests/fixtures"))
        empty_records = [r for r in result.records if r.project == "empty-project"]
        assert len(empty_records) == 0

    def test_scan_directory_project_alpha_tokens(self):
        """project-alpha aggregates to correct token totals."""
        result = scan_directory(Path("tests/fixtures"))
        alpha_records = [r for r in result.records if r.project == "project-alpha"]
        inp = sum(r.input_tokens for r in alpha_records)
        out = sum(r.output_tokens for r in alpha_records)
        cw = sum(r.cache_creation_tokens for r in alpha_records)
        cr = sum(r.cache_read_tokens for r in alpha_records)
        assert inp == 5800
        assert out == 1150
        assert cw == 2250
        assert cr == 4600

    def test_scan_directory_project_beta_tokens(self):
        """project-beta aggregates to correct token totals."""
        result = scan_directory(Path("tests/fixtures"))
        beta_records = [r for r in result.records if r.project == "project-beta"]
        inp = sum(r.input_tokens for r in beta_records)
        out = sum(r.output_tokens for r in beta_records)
        cw = sum(r.cache_creation_tokens for r in beta_records)
        cr = sum(r.cache_read_tokens for r in beta_records)
        assert inp == 21000
        assert out == 4050
        assert cw == 9000
        assert cr == 14400

    def test_scan_directory_all_records_have_model(self):
        """Every record has a model field set."""
        result = scan_directory(Path("tests/fixtures"))
        assert all(r.model for r in result.records)

    def test_scan_directory_all_records_have_timestamp(self):
        """Every record has a timestamp field set."""
        result = scan_directory(Path("tests/fixtures"))
        assert all(r.timestamp is not None for r in result.records)

    def test_scan_directory_nonexistent_path(self):
        """Scanning a nonexistent directory returns empty result."""
        result = scan_directory(Path("/nonexistent/path"))
        assert result.records == []
        assert result.skipped_lines == 0
        assert result.scanned_files == 0

    def test_scan_directory_sorted_order(self):
        """Projects are scanned in sorted order."""
        result = scan_directory(Path("tests/fixtures"))
        projects = [r.project for r in result.records]
        unique_projects = []
        for p in projects:
            if p not in unique_projects:
                unique_projects.append(p)
        assert unique_projects == sorted(unique_projects)

    def test_scan_directory_models_include_fable(self):
        """scan_directory includes claude-fable-5 records from project-beta."""
        result = scan_directory(Path("tests/fixtures"))
        models = {r.model for r in result.records}
        assert "claude-fable-5" in models

    def test_scan_directory_models_include_synthetic(self):
        """scan_directory includes <synthetic> model from session-003."""
        result = scan_directory(Path("tests/fixtures"))
        models = {r.model for r in result.records}
        assert "<synthetic>" in models
