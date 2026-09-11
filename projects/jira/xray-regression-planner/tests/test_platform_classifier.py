"""classify_platforms assigns platforms from labels and summary text."""

from __future__ import annotations

from engine.platform_classifier import classify_platforms
from models.test_case import Platform

from tests.fixtures.sample_data import PLATFORM_LABELS, make_test_case


def test_classifies_from_labels():
    tests = [make_test_case(labels=["web"])]
    classify_platforms(tests, PLATFORM_LABELS)
    assert tests[0].platforms == [Platform.WEB]


def test_classifies_from_summary_when_labels_are_empty():
    # Summary text is the fallback signal; a case labelled by nobody still
    # needs a platform or it silently lands in the UNKNOWN bucket.
    tests = [make_test_case(summary="Sign in on android device", labels=[])]
    classify_platforms(tests, PLATFORM_LABELS)
    assert tests[0].platforms == [Platform.ANDROID]


def test_assigns_multiple_platforms_when_several_match():
    tests = [make_test_case(summary="Checkout on web and ios", labels=[])]
    classify_platforms(tests, PLATFORM_LABELS)
    assert set(tests[0].platforms) == {Platform.WEB, Platform.IOS}


def test_falls_back_to_unknown_rather_than_guessing():
    tests = [make_test_case(summary="Something unclassifiable", labels=[])]
    classify_platforms(tests, PLATFORM_LABELS)
    assert tests[0].platforms == [Platform.UNKNOWN]


def test_matching_is_case_insensitive():
    tests = [make_test_case(labels=["WEB"], summary="")]
    classify_platforms(tests, PLATFORM_LABELS)
    assert tests[0].platforms == [Platform.WEB]


def test_handles_an_empty_input_list():
    tests = []
    classify_platforms(tests, PLATFORM_LABELS)
    assert tests == []
