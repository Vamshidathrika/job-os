"""Unit tests for policy enforcement (LinkedIn, Multi-Tenant, Compliance)."""

import pytest

from jobos.policy import PolicyViolation
from jobos.policy.linkedin import NEVER_AUTOMATE, AUTONOMOUS, assert_action_allowed
from jobos.policy.compliance import gdpr_art14_footer, dpdp_notice, hash_email_for_suppression
from jobos.policy.multi_tenant import (
    assert_no_application_layer_only_filtering,
    assert_credential_redacted,
    assert_no_suppression_override,
    assert_cross_family_for_autonomous_tailoring,
    assert_prompt_is_versioned,
    assert_no_cross_tenant_people_sharing,
    assert_new_tenant_in_shadow_mode,
)


def test_linkedin_never_automate_actions_raise_violation() -> None:
    """Prohibited LinkedIn actions must raise PolicyViolation."""
    for action in NEVER_AUTOMATE:
        with pytest.raises(PolicyViolation):
            assert_action_allowed(action)


def test_linkedin_autonomous_actions_allowed() -> None:
    """Allowed LinkedIn actions must pass without error."""
    for action in AUTONOMOUS:
        assert_action_allowed(action)  # Should not raise


def test_gdpr_art14_footer_contains_source() -> None:
    """GDPR Art. 14 disclosure footer must state the tenant, company, and data source."""
    footer = gdpr_art14_footer("Tenant Corp", "Acme Inc", "Apollo.io")
    assert "Tenant Corp" in footer
    assert "Acme Inc" in footer
    assert "Apollo.io" in footer


def test_dpdp_notice_contains_deletion_rights() -> None:
    """DPDP Act notice must mention tenant name and deletion rights."""
    notice = dpdp_notice("Tenant Corp")
    assert "Tenant Corp" in notice
    assert "DPDP Act" in notice
    assert "deletion" in notice


def test_hash_email_for_suppression() -> None:
    """Email hashing for suppression list must be SHA-256 of lowercased trimmed email."""
    hash1 = hash_email_for_suppression(" Test@Example.com ")
    hash2 = hash_email_for_suppression("test@example.com")
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex string length


def test_multi_tenant_prohibitions() -> None:
    """Test all 7 multi-tenant prohibitions raise PolicyViolation when violated."""
    with pytest.raises(PolicyViolation):
        assert_no_application_layer_only_filtering(has_rls=False)

    with pytest.raises(PolicyViolation):
        assert_credential_redacted(has_credential_in_log=True)

    with pytest.raises(PolicyViolation):
        assert_no_suppression_override(override_attempted=True)

    with pytest.raises(PolicyViolation):
        assert_cross_family_for_autonomous_tailoring(same_family=True)

    with pytest.raises(PolicyViolation):
        assert_prompt_is_versioned(is_versioned=False)

    with pytest.raises(PolicyViolation):
        assert_no_cross_tenant_people_sharing(sharing_attempted=True)

    with pytest.raises(PolicyViolation):
        assert_new_tenant_in_shadow_mode(days_in_shadow=3)
