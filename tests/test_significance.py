"""
Tests for change significance.

The point of the classifier is that a person reading the change feed sees the
40% price cut before the corrected typo. These tests pin the ordering and the
boundaries, because the thresholds are the whole product: get them wrong and
the feed is either noise or silence.
"""

from __future__ import annotations

import pytest

from app.analysis.significance import (
    COSMETIC,
    CRITICAL,
    LARGE_PRICE_MOVE,
    MINOR,
    NOTABLE,
    ChangeAssessment,
    classify,
    sort_key,
)


def diff(field, old, new):
    return {"field": field, "old": old, "new": new}


class TestPriceMovement:
    def test_a_large_drop_is_critical(self):
        assert classify([diff("price_incl_tax", 50.0, 30.0)]).severity == CRITICAL

    def test_a_large_rise_is_also_critical(self):
        # Direction does not decide urgency: a sudden rise is as likely to be
        # a data error as a repricing, and both want a human.
        assert classify([diff("price_incl_tax", 30.0, 50.0)]).severity == CRITICAL

    def test_a_moderate_move_is_notable(self):
        assert classify([diff("price_incl_tax", 100.0, 90.0)]).severity == NOTABLE

    def test_a_rounding_level_move_is_minor(self):
        assert classify([diff("price_incl_tax", 100.0, 101.0)]).severity == MINOR

    def test_the_threshold_boundary_is_pinned(self):
        # Exactly at the threshold counts as the larger band. Pinning it stops
        # the comparison silently flipping to > during a later edit.
        at = 100.0 * (1 - LARGE_PRICE_MOVE)
        assert classify([diff("price_incl_tax", 100.0, at)]).severity == CRITICAL

    def test_the_reason_states_the_numbers(self):
        reason = classify([diff("price_incl_tax", 50.0, 30.0)]).reasons[0]
        assert "50.00" in reason and "30.00" in reason and "40%" in reason

    def test_a_price_from_zero_does_not_divide_by_zero(self):
        assessment = classify([diff("price_incl_tax", 0, 25.0)])
        assert assessment.severity == NOTABLE
        assert assessment.signals.get("price_from_zero") is True

    def test_the_two_price_fields_are_reported_once(self):
        assessment = classify(
            [diff("price_incl_tax", 50.0, 30.0), diff("price_excl_tax", 45.0, 27.0)]
        )
        price_reasons = [r for r in assessment.reasons if "price" in r]
        assert len(price_reasons) == 1

    def test_an_unparseable_price_is_ignored_rather_than_crashing(self):
        assert classify([diff("price_incl_tax", "n/a", 30.0)]).severity in {
            MINOR, NOTABLE, CRITICAL, COSMETIC
        }


class TestStock:
    def test_going_out_of_stock_is_critical(self):
        assert classify([diff("availability", 12, 0)]).severity == CRITICAL

    def test_coming_back_into_stock_is_notable(self):
        assert classify([diff("availability", 0, 9)]).severity == NOTABLE

    def test_dropping_to_a_low_level_is_notable(self):
        assert classify([diff("availability", 40, 3)]).severity == NOTABLE

    def test_an_ordinary_stock_movement_is_minor(self):
        assert classify([diff("availability", 40, 30)]).severity == MINOR

    def test_the_in_stock_flag_is_honoured(self):
        assert classify([diff("in_stock", True, False)]).severity == CRITICAL


class TestCosmetic:
    def test_a_description_edit_alone_is_cosmetic(self):
        assert classify([diff("description", "teh book", "the book")]).severity == COSMETIC

    def test_an_image_swap_alone_is_cosmetic(self):
        assert classify([diff("image_url", "a.jpg", "b.jpg")]).severity == COSMETIC

    def test_cosmetic_plus_substantive_is_not_cosmetic(self):
        # The whole failure mode being avoided: a real change hidden because a
        # trivial one was recorded in the same crawl.
        assessment = classify(
            [diff("description", "x", "y"), diff("availability", 10, 0)]
        )
        assert assessment.severity == CRITICAL

    def test_the_cosmetic_field_is_still_mentioned(self):
        assessment = classify(
            [diff("description", "x", "y"), diff("availability", 10, 0)]
        )
        assert any("description" in r for r in assessment.reasons)


class TestSeverityCombination:
    def test_the_worst_signal_wins(self):
        assessment = classify(
            [diff("price_incl_tax", 50.0, 20.0), diff("availability", 8, 0)]
        )
        assert assessment.severity == CRITICAL
        assert len(assessment.reasons) >= 2

    def test_a_serious_signal_is_not_diluted_by_trivia(self):
        assessment = classify(
            [
                diff("availability", 10, 0),
                diff("num_reviews", 3, 4),
                diff("rating", 4, 4 - 1),
            ]
        )
        assert assessment.severity == CRITICAL


class TestNewTitles:
    def test_a_new_book_is_notable(self):
        assert classify([], change_type="new").severity == NOTABLE

    def test_a_new_book_says_so(self):
        assert "new title" in classify([], change_type="new").reasons[0].lower()


class TestOrdering:
    def test_worst_first(self):
        assessments = [
            classify([diff("description", "x", "y")]),
            classify([diff("availability", 12, 0)]),
            classify([diff("num_reviews", 1, 2)]),
        ]
        ordered = sorted(assessments, key=sort_key)
        assert ordered[0].severity == CRITICAL
        assert ordered[-1].severity == COSMETIC

    def test_bigger_price_moves_rank_above_smaller_ones(self):
        small = classify([diff("price_incl_tax", 100.0, 75.0)])
        large = classify([diff("price_incl_tax", 100.0, 20.0)])
        assert sorted([small, large], key=sort_key)[0] is large


class TestInputShapes:
    def test_it_accepts_pydantic_style_objects(self):
        # The crawler stores FieldDiff models; the API reads plain dicts back
        # out of Mongo. Both must work.
        class FieldDiff:
            def __init__(self, field, old, new):
                self.field, self.old, self.new = field, old, new

        assert classify([FieldDiff("availability", 5, 0)]).severity == CRITICAL

    def test_an_empty_diff_is_cosmetic_not_an_error(self):
        assert classify([]).severity == COSMETIC

    def test_the_assessment_serialises(self):
        payload = classify([diff("availability", 5, 0)]).as_dict()
        assert set(payload) == {"severity", "reasons", "signals"}
