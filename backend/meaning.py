"""Compatibility imports for V3 offline tools; runtime implementation lives in ai."""
from ai.humanizer.meaning import (  # noqa: F401
    SCALAR, UNIT, QUANTITY_PATTERN, QUANTITIES, UNIT_SUFFIX, QUANTITY_BASE, SUFFIX,
    UNSIGNED_SCALAR, SIGNED_SCALAR, SIGNED_EXPRESSIONS, QUOTED_OR_REFERENCE,
    MARKERS, COMPILED_MARKERS, marker_counts, changed_risk_categories,
)
