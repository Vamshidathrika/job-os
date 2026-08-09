"""Multi-tenant prohibitions enforcement (v3.1 Addendum §10 Rules 11-17)."""

from __future__ import annotations

from jobos.policy import PolicyViolation

PROHIBITIONS: list[str] = [
    "Rule 11: No application-layer-only tenant filtering. RLS or it doesn't ship.",
    "Rule 12: No credential in any log, trace, error, or LLM prompt. Allowlist redaction at boundary.",
    "Rule 13: No per-tenant override of the global suppression list. Ever.",
    "Rule 14: No autonomous tailoring when tailor and verifier resolve to same model family. Band C only.",
    "Rule 15: No unstaged prompt changes. A prompt is a deploy.",
    "Rule 16: No sharing of people or evidence_items across tenants.",
    "Rule 17: No new tenant starting above shadow mode. Seven days minimum.",
]


def assert_no_application_layer_only_filtering(has_rls: bool) -> None:
    """Rule 11: RLS is mandatory for all tenant tables."""
    if not has_rls:
        raise PolicyViolation("Rule 11 Violation: RLS is required on all tenant tables.")


def assert_credential_redacted(has_credential_in_log: bool) -> None:
    """Rule 12: Credentials must never appear in logs or traces."""
    if has_credential_in_log:
        raise PolicyViolation("Rule 12 Violation: Plaintext credential found in log boundary.")


def assert_no_suppression_override(override_attempted: bool) -> None:
    """Rule 13: Global suppression list cannot be overridden per-tenant."""
    if override_attempted:
        raise PolicyViolation("Rule 13 Violation: Per-tenant override of global suppression list is forbidden.")


def assert_cross_family_for_autonomous_tailoring(same_family: bool) -> None:
    """Rule 14: Dual-family LLM required for autonomous tailoring."""
    if same_family:
        raise PolicyViolation("Rule 14 Violation: Same model family for tailor/verifier. Forced to Band C.")


def assert_prompt_is_versioned(is_versioned: bool) -> None:
    """Rule 15: A prompt is a deploy — must be git-versioned."""
    if not is_versioned:
        raise PolicyViolation("Rule 15 Violation: Unstaged/unversioned prompt detected.")


def assert_no_cross_tenant_people_sharing(sharing_attempted: bool) -> None:
    """Rule 16: Never share people or evidence_items across tenants."""
    if sharing_attempted:
        raise PolicyViolation("Rule 16 Violation: Cross-tenant sharing of people or evidence_items is forbidden.")


def assert_new_tenant_in_shadow_mode(days_in_shadow: int) -> None:
    """Rule 17: New tenants must spend at least 7 days in shadow mode."""
    if days_in_shadow < 7:
        raise PolicyViolation("Rule 17 Violation: New tenant must be in shadow mode for at least 7 days.")
