"""
Change significance: which of today's changes are worth a human's attention.

The crawler already detects *that* a book changed and records a field-level
diff. On a catalogue of a thousand titles that produces hundreds of daily
change rows, all presented as equals: a price cut of 40% sits in the same list
as a corrected typo in a description. A monitor nobody reads is a monitor that
does not work, and undifferentiated alerts are the standard way monitors stop
being read.

This classifies each change into a severity a person can filter on, and states
the reason in words rather than leaving the reader to compare two JSON blobs.

**Rules, not a model.** "Did the price move more than 20%?" and "did this go
out of stock?" have exact answers. A classifier would need labelled examples
nobody has, would be wrong occasionally in ways nobody could predict, and
would be slower and more expensive than the arithmetic. The place a model
genuinely helps here is judging whether a *description* rewrite changed the
meaning or only the wording, which is noted as a limitation rather than
pretended at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

# Severity ordering, most urgent first. The strings are the API contract.
CRITICAL = "critical"
NOTABLE = "notable"
MINOR = "minor"
COSMETIC = "cosmetic"

SEVERITY_ORDER = {CRITICAL: 0, NOTABLE: 1, MINOR: 2, COSMETIC: 3}

#: Price movement thresholds, as fractions.
LARGE_PRICE_MOVE = 0.20
SMALL_PRICE_MOVE = 0.05

#: Stock level below which a drop is worth flagging.
LOW_STOCK = 5

#: Fields whose change carries no commercial meaning on its own.
COSMETIC_FIELDS = {"image_url", "description"}


@dataclass
class ChangeAssessment:
    severity: str
    reasons: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "reasons": self.reasons,
            "signals": self.signals,
        }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _diff_map(diffs: Iterable[Mapping[str, Any]]) -> dict[str, tuple[Any, Any]]:
    """Field name → (old, new). Accepts dicts or FieldDiff-like objects."""
    out: dict[str, tuple[Any, Any]] = {}
    for diff in diffs:
        if isinstance(diff, Mapping):
            name, old, new = diff.get("field"), diff.get("old"), diff.get("new")
        else:
            name, old, new = (
                getattr(diff, "field", None),
                getattr(diff, "old", None),
                getattr(diff, "new", None),
            )
        if name:
            out[name] = (old, new)
    return out


def assess_price(old: Any, new: Any) -> tuple[str | None, str | None, dict]:
    """Classify a price movement. Returns (severity, reason, signals)."""
    old_price, new_price = _as_float(old), _as_float(new)
    if old_price is None or new_price is None:
        return None, None, {}
    if old_price == 0:
        # A move away from zero is meaningful, but the percentage is not
        # defined — reporting an infinite change would be worse than saying so.
        return (NOTABLE, f"price set to {new_price:.2f} from zero", {"price_from_zero": True})

    delta = (new_price - old_price) / old_price
    signals = {
        "price_old": old_price,
        "price_new": new_price,
        "price_change_pct": round(delta * 100, 2),
    }
    direction = "rose" if delta > 0 else "fell"
    magnitude = abs(delta)

    if magnitude >= LARGE_PRICE_MOVE:
        return (
            CRITICAL,
            f"price {direction} {magnitude:.0%} ({old_price:.2f} → {new_price:.2f})",
            signals,
        )
    if magnitude >= SMALL_PRICE_MOVE:
        return (
            NOTABLE,
            f"price {direction} {magnitude:.0%} ({old_price:.2f} → {new_price:.2f})",
            signals,
        )
    return (
        MINOR,
        f"price {direction} {magnitude:.1%} ({old_price:.2f} → {new_price:.2f})",
        signals,
    )


def assess_stock(old: Any, new: Any) -> tuple[str | None, str | None, dict]:
    """Classify an availability movement."""
    old_qty, new_qty = _as_int(old), _as_int(new)
    if old_qty is None or new_qty is None:
        return None, None, {}

    signals = {"availability_old": old_qty, "availability_new": new_qty}

    if old_qty > 0 and new_qty == 0:
        return CRITICAL, "went out of stock", signals
    if old_qty == 0 and new_qty > 0:
        return NOTABLE, f"back in stock ({new_qty} available)", signals
    if new_qty < old_qty and new_qty <= LOW_STOCK:
        return NOTABLE, f"stock low: {old_qty} → {new_qty}", signals
    if new_qty != old_qty:
        return MINOR, f"stock changed: {old_qty} → {new_qty}", signals
    return None, None, signals


def classify(diffs: Iterable[Mapping[str, Any]], change_type: str = "update") -> ChangeAssessment:
    """
    Assess one change log entry.

    The severity is the most urgent of the individual signals: a change that
    both dropped the price 30% and went out of stock is critical, and taking a
    maximum rather than an average is what keeps a serious signal from being
    diluted by trivia recorded in the same crawl.
    """
    if change_type == "new":
        return ChangeAssessment(
            severity=NOTABLE,
            reasons=["new title appeared in the catalogue"],
            signals={"change_type": "new"},
        )

    fields = _diff_map(diffs)
    if not fields:
        return ChangeAssessment(severity=COSMETIC, reasons=["no field-level changes recorded"])

    severities: list[str] = []
    reasons: list[str] = []
    signals: dict[str, Any] = {}

    for price_field in ("price_incl_tax", "price_excl_tax"):
        if price_field in fields:
            severity, reason, extra = assess_price(*fields[price_field])
            if severity:
                severities.append(severity)
                reasons.append(reason)
                signals.update(extra)
            break  # the two prices move together; report once

    if "availability" in fields:
        severity, reason, extra = assess_stock(*fields["availability"])
        if severity:
            severities.append(severity)
            reasons.append(reason)
        signals.update(extra)

    if "in_stock" in fields:
        old, new = fields["in_stock"]
        if old and not new:
            severities.append(CRITICAL)
            reasons.append("marked out of stock")
        elif new and not old:
            severities.append(NOTABLE)
            reasons.append("marked back in stock")

    if "name" in fields:
        # A title change on a stable identifier usually means the listing was
        # replaced rather than edited, which is worth a look.
        severities.append(NOTABLE)
        reasons.append(f"title changed: {fields['name'][0]!r} → {fields['name'][1]!r}")

    if "category" in fields:
        severities.append(MINOR)
        reasons.append(f"recategorised: {fields['category'][0]} → {fields['category'][1]}")

    if "rating" in fields:
        old, new = _as_int(fields["rating"][0]), _as_int(fields["rating"][1])
        if old is not None and new is not None:
            severities.append(MINOR)
            reasons.append(f"rating {old} → {new}")

    if "num_reviews" in fields:
        severities.append(MINOR)
        reasons.append(f"review count {fields['num_reviews'][0]} → {fields['num_reviews'][1]}")

    cosmetic_only = set(fields) <= COSMETIC_FIELDS
    if cosmetic_only:
        changed = ", ".join(sorted(fields))
        return ChangeAssessment(
            severity=COSMETIC,
            reasons=[f"only {changed} changed"],
            signals={"fields_changed": sorted(fields)},
        )

    for name in sorted(set(fields) & COSMETIC_FIELDS):
        reasons.append(f"{name} also changed")

    if not severities:
        return ChangeAssessment(
            severity=MINOR,
            reasons=reasons or [f"changed: {', '.join(sorted(fields))}"],
            signals=signals,
        )

    severity = min(severities, key=lambda s: SEVERITY_ORDER[s])
    signals["fields_changed"] = sorted(fields)
    return ChangeAssessment(severity=severity, reasons=reasons, signals=signals)


def sort_key(assessment: ChangeAssessment) -> tuple[int, float]:
    """Worst first, then by the size of the price move."""
    return (
        SEVERITY_ORDER.get(assessment.severity, 9),
        -abs(assessment.signals.get("price_change_pct", 0) or 0),
    )
