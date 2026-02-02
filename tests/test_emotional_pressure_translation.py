"""Tests for emotional pressure translation layer in the Telegram bot SYSTEM_PROMPT."""
import pytest
from src.telegram_bot import SYSTEM_PROMPT


class TestEmotionalPressureTranslation:
    """Test the emotional pressure translation functionality in the system prompt."""

    def test_system_prompt_contains_emotional_pressure_section(self):
        """Verify the SYSTEM_PROMPT contains the enhanced emotional pressure section."""
        assert "**Emotional pressure:**" in SYSTEM_PROMPT

    def test_desperation_language_detection_specified(self):
        """Verify specific desperation language patterns are listed."""
        desperation_patterns = [
            "I need to win back",
            "all in",
            "can't afford to lose",
            "must",
            "last chance",
            "YOLO",
            "desperate",
            "broke",
            "final shot"
        ]

        for pattern in desperation_patterns:
            assert pattern in SYSTEM_PROMPT, f"Pattern '{pattern}' not found in SYSTEM_PROMPT"

    def test_emotion_to_numbers_conversion_specified(self):
        """Verify instructions for converting emotion to numbers are present."""
        number_conversion_instructions = [
            "Convert emotion → numbers",
            "ranges",
            "probabilities",
            "caps",
            "specific targets"
        ]

        for instruction in number_conversion_instructions:
            assert instruction in SYSTEM_PROMPT, f"Instruction '{instruction}' not found in SYSTEM_PROMPT"

    def test_no_catch_up_trading_specified(self):
        """Verify instructions against catch-up trading are present."""
        anti_catchup_instructions = [
            "Never suggest increasing size or risk to \"catch up\"",
            "No doubling down",
            "revenge trades",
            "higher leverage when stressed"
        ]

        for instruction in anti_catchup_instructions:
            assert instruction in SYSTEM_PROMPT, f"Anti-catchup instruction '{instruction}' not found in SYSTEM_PROMPT"

    def test_risk_context_usage_specified(self):
        """Verify instructions to use portfolio analysis for risk context."""
        risk_context_instructions = [
            "Use risk context",
            "get_portfolio_analysis",
            "current drawdown",
            "kill switch status",
            "Given current drawdown, consider waiting",
            "With kill switch active, focus on preservation"
        ]

        for instruction in risk_context_instructions:
            assert instruction in SYSTEM_PROMPT, f"Risk context instruction '{instruction}' not found in SYSTEM_PROMPT"

    def test_cooling_off_suggestions_specified(self):
        """Verify instructions for cooling off suggestions are present."""
        cooling_off_instructions = [
            "Suggest cooling off",
            "reducing exposure",
            "trim by 50%",
            "wait 24-48 hours",
            "paper trading only"
        ]

        for instruction in cooling_off_instructions:
            assert instruction in SYSTEM_PROMPT, f"Cooling off instruction '{instruction}' not found in SYSTEM_PROMPT"

    def test_structure_compression_example_provided(self):
        """Verify concrete example of compressing desperation into structure."""
        example_transformation = [
            "Compress desperation into structure",
            "I'm all in on this trade",
            "Consider 5-10% allocation with defined exit at -20% loss"
        ]

        for example in example_transformation:
            assert example in SYSTEM_PROMPT, f"Structure compression example '{example}' not found in SYSTEM_PROMPT"

    def test_emotional_pressure_section_is_complete(self):
        """Verify the emotional pressure section contains all required components."""
        # Check that the section has numbered items (1-5) as expected
        numbered_items = [
            "1. **Convert emotion → numbers**",
            "2. **Never suggest increasing size or risk to \"catch up\"**",
            "3. **Use risk context**",
            "4. **Suggest cooling off**",
            "5. **Compress desperation into structure**"
        ]

        for item in numbered_items:
            assert item in SYSTEM_PROMPT, f"Numbered item '{item}' not found in SYSTEM_PROMPT"

    def test_system_prompt_maintains_existing_structure(self):
        """Verify that adding emotional pressure section doesn't break existing structure."""
        # Check that other important sections are still present
        existing_sections = [
            "**Persona:**",
            "**Recommendations:**",
            "**Manual trades:**",
            "**Option trade accuracy:**",
            "**Format (Telegram):**"
        ]

        for section in existing_sections:
            assert section in SYSTEM_PROMPT, f"Existing section '{section}' not found in SYSTEM_PROMPT"