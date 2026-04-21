"""Tests for agent generation guide — verifies clarification section."""

import importlib
from pathlib import Path

from backend.copilot import prompting


class TestGetSdkSupplementStaticPlaceholder:
    """get_sdk_supplement must return a static string so the system prompt is
    identical for all users and sessions, enabling cross-user prompt-cache hits.
    """

    def setup_method(self):
        # Reset the module-level singleton before each test so tests are isolated.
        importlib.reload(prompting)

    def test_local_mode_uses_placeholder_not_uuid(self):
        result = prompting.get_sdk_supplement(use_e2b=False)
        assert "/tmp/copilot-<session-id>" in result

    def test_local_mode_is_idempotent(self):
        first = prompting.get_sdk_supplement(use_e2b=False)
        second = prompting.get_sdk_supplement(use_e2b=False)
        assert first == second, "Supplement must be identical across calls"

    def test_e2b_mode_uses_home_user(self):
        result = prompting.get_sdk_supplement(use_e2b=True)
        assert "/home/user" in result

    def test_e2b_mode_has_no_session_placeholder(self):
        result = prompting.get_sdk_supplement(use_e2b=True)
        assert "<session-id>" not in result


class TestAgentGenerationGuideContainsClarifySection:
    """The agent generation guide must include the clarification section."""

    def test_guide_includes_clarify_section(self):
        guide_path = Path(__file__).parent / "sdk" / "agent_generation_guide.md"
        content = guide_path.read_text(encoding="utf-8")
        assert "Before or During Building" in content

    def test_guide_mentions_find_block_for_clarification(self):
        guide_path = Path(__file__).parent / "sdk" / "agent_generation_guide.md"
        content = guide_path.read_text(encoding="utf-8")
        clarify_section = content.split("Before or During Building")[1].split(
            "### Workflow"
        )[0]
        assert "find_block" in clarify_section

    def test_guide_mentions_ask_question_tool(self):
        guide_path = Path(__file__).parent / "sdk" / "agent_generation_guide.md"
        content = guide_path.read_text(encoding="utf-8")
        clarify_section = content.split("Before or During Building")[1].split(
            "### Workflow"
        )[0]
        assert "ask_question" in clarify_section


class TestBaselineWebSearchSupplement:
    """The fast-mode web-search supplement must point at block IDs that
    actually exist and name each block's required input fields, so the
    Kimi / baseline model can call them via ``run_block`` without a
    ``find_block`` round-trip.  Pinning the block IDs against the live
    registry means a block rename / delete breaks this test rather than
    shipping a dead UUID to the model."""

    def test_perplexity_block_id_matches_registered_block(self):
        from backend.blocks.perplexity import PerplexityBlock

        assert PerplexityBlock().id == prompting.PERPLEXITY_BLOCK_ID

    def test_send_web_request_block_id_matches_registered_block(self):
        from backend.blocks.http import SendWebRequestBlock

        assert SendWebRequestBlock().id == prompting.SEND_WEB_REQUEST_BLOCK_ID

    def test_supplement_surfaces_both_block_ids(self):
        text = prompting.get_baseline_web_search_supplement()
        assert prompting.PERPLEXITY_BLOCK_ID in text
        assert prompting.SEND_WEB_REQUEST_BLOCK_ID in text

    def test_supplement_names_required_inputs(self):
        text = prompting.get_baseline_web_search_supplement()
        # Perplexity required input.
        assert '"prompt"' in text
        # SendWebRequest required input.
        assert '"url"' in text

    def test_supplement_uses_perplexitymodel_enum_values_verbatim(self):
        """Regression: the earlier supplement invented bare sonar IDs
        (``"sonar"``, ``"sonar-reasoning"``, ``"sonar-reasoning-pro"``)
        that don't match ``PerplexityModel`` values — every call logged
        an ``Invalid PerplexityModel`` warning and silently fell back to
        plain ``sonar``.  The supplement must now list exactly the enum
        values, in full provider-prefixed form, and the default must
        equal ``PerplexityModel.SONAR.value``."""
        from backend.blocks.perplexity import PerplexityModel

        text = prompting.get_baseline_web_search_supplement()
        # Every enum value surfaces verbatim.
        for model in PerplexityModel:
            assert (
                model.value in text
            ), f"Supplement missing {model.value!r} (known PerplexityModel value)"
        # The default example carries the provider prefix so Kimi can
        # pass it through without the fallback warning firing.
        assert f'"model": "{PerplexityModel.SONAR.value}"' in text

    def test_supplement_does_not_mention_invented_sonar_variants(self):
        """Regression: these bare strings were listed as valid Perplexity
        models before the enum-driven rewrite — none match a real
        ``PerplexityModel`` value, so the block silently fell back to
        ``SONAR`` on every call.  Guard against the next reader
        accidentally reintroducing them."""
        text = prompting.get_baseline_web_search_supplement()
        # ``sonar-reasoning`` / ``sonar-reasoning-pro`` are not enum
        # members today — if upstream adds them, re-enable this check
        # alongside an ``assert PerplexityModel.SONAR_REASONING ...``.
        assert "sonar-reasoning" not in text
        # Bare ``"sonar"`` without the ``perplexity/`` prefix is rejected
        # by the block's model validator; the enum-driven supplement
        # should emit only the provider-prefixed form.  Check the
        # quote-wrapped bare form to avoid matching ``perplexity/sonar``.
        assert '"sonar"' not in text
        assert '"sonar-pro"' not in text

    def test_supplement_flags_credentials_dependency(self):
        text = prompting.get_baseline_web_search_supplement()
        assert "credentials" in text.lower()
        assert "connect_integration" in text
