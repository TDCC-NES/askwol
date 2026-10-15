"""Shared check identities, ordering, and numbering."""

from itertools import groupby

from askwol.checks import (
    CHECK_CATEGORIES,
    CHECK_NUMBERS,
    CHECKS,
    CLUSTER_NUMBERS,
    GUIDE_CHECK_NUMBERS,
)


def test_catalogue_has_unique_anchors_and_ordered_categories():
    assert len({check["report_anchor"] for check in CHECKS}) == len(CHECKS)
    assert len({check["guide_anchor"] for check in CHECKS}) == len(CHECKS)
    categories = [category["key"] for category in CHECK_CATEGORIES]
    assert len(set(categories)) == len(categories)
    assert [category for category, _ in groupby(check["category"] for check in CHECKS)] == categories
    assert all(check["description"].strip() for check in CHECKS)


def test_report_and_guide_numbers_follow_category_order():
    for cluster_number, category in enumerate(CHECK_CATEGORIES, start=1):
        assert CLUSTER_NUMBERS[category["key"]] == cluster_number
        checks = [check for check in CHECKS if check["category"] == category["key"]]
        for position, check in enumerate(checks, start=1):
            expected = f"{cluster_number}.{position}"
            assert CHECK_NUMBERS[check["report_anchor"]] == expected
            assert GUIDE_CHECK_NUMBERS[check["guide_anchor"]] == expected
