"""Normalization helpers for messy Jira data."""

from __future__ import annotations

from ingestion.normalizer import UNCATEGORIZED, normalize_component_name, normalize_labels


def test_trims_component_whitespace():
    assert normalize_component_name("  Checkout  ") == "Checkout"


def test_empty_component_becomes_uncategorized():
    # An unassigned component must land somewhere nameable — dropping it would
    # silently remove the item from every per-component aggregate downstream.
    assert normalize_component_name("") == UNCATEGORIZED
    assert normalize_component_name("   ") == UNCATEGORIZED


def test_deduplicates_labels_case_insensitively():
    assert normalize_labels(["Web", "web", "WEB"]) == ["Web"]


def test_preserves_original_casing_of_first_occurrence():
    assert normalize_labels(["Checkout", "checkout", "Auth"]) == ["Checkout", "Auth"]


def test_drops_blank_labels():
    assert normalize_labels(["web", "", "   ", "ios"]) == ["web", "ios"]


def test_preserves_order():
    assert normalize_labels(["c", "a", "b"]) == ["c", "a", "b"]
