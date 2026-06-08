"""Selector-map coverage for apply-assist runner."""
from __future__ import annotations

from jobforge.application_agent.base import ATSPlatform
from jobforge.application_agent.browser import (
    FILLABLE_FIELDS_ORDER,
    SelectorSpec,
    selector_for,
    selectors_for,
    supported_platforms,
)


def test_supported_platforms_excludes_unknown() -> None:
    sup = supported_platforms()
    assert ATSPlatform.UNKNOWN not in sup
    assert ATSPlatform.GREENHOUSE in sup
    assert ATSPlatform.LEVER in sup
    assert ATSPlatform.ASHBY in sup


def test_each_supported_platform_has_email_and_submit() -> None:
    for p in supported_platforms():
        m = selectors_for(p)
        assert "email" in m, f"{p}: no email selector"
        assert "submit" in m, f"{p}: no submit selector"


def test_each_supported_platform_has_resume_file_selector() -> None:
    for p in supported_platforms():
        spec = selector_for(p, "resume")
        assert spec is not None
        assert spec.kind == "file"


def test_each_submit_selector_marked_submit_kind() -> None:
    for p in supported_platforms():
        spec = selector_for(p, "submit")
        assert spec is not None and spec.kind == "submit"


def test_greenhouse_uses_first_and_last_name() -> None:
    assert selector_for(ATSPlatform.GREENHOUSE, "first_name") is not None
    assert selector_for(ATSPlatform.GREENHOUSE, "last_name") is not None
    # Greenhouse has no combined-name field.
    assert selector_for(ATSPlatform.GREENHOUSE, "name") is None


def test_lever_uses_combined_name_field() -> None:
    assert selector_for(ATSPlatform.LEVER, "name") is not None
    # Lever should NOT expose split first/last (the runner relies on this).
    assert selector_for(ATSPlatform.LEVER, "first_name") is None
    assert selector_for(ATSPlatform.LEVER, "last_name") is None


def test_ashby_uses_camelcase_split_name() -> None:
    fn = selector_for(ATSPlatform.ASHBY, "first_name")
    ln = selector_for(ATSPlatform.ASHBY, "last_name")
    assert fn is not None and "firstName" in fn.primary
    assert ln is not None and "lastName" in ln.primary


def test_selectors_for_unknown_is_empty_dict_not_none() -> None:
    m = selectors_for(ATSPlatform.UNKNOWN)
    assert isinstance(m, dict)
    assert m == {}


def test_fallbacks_are_always_a_tuple() -> None:
    for p in supported_platforms():
        for spec in selectors_for(p).values():
            assert isinstance(spec.fallbacks, tuple)


def test_candidates_includes_primary_first_then_fallbacks() -> None:
    spec = SelectorSpec("a", ("b", "c"))
    assert spec.candidates() == ("a", "b", "c")


def test_fillable_fields_order_does_not_include_submit() -> None:
    assert "submit" not in FILLABLE_FIELDS_ORDER


def test_fillable_fields_order_lists_logical_keys_used_by_at_least_one_platform() -> None:
    used: set[str] = set()
    for p in supported_platforms():
        used.update(selectors_for(p).keys())
    used.discard("submit")
    for field in FILLABLE_FIELDS_ORDER:
        assert field in used, f"{field} not used by any platform but listed in order"
