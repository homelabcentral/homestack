"""Tests for `.env.template` Pydantic models."""

import pytest
from models import (
    EnvTemplateChoice,
    EnvTemplateValueType,
    EnvTemplateVariable,
    EnvValueKind,
)
from pydantic import ValidationError


class TestEnvTemplateValueType:
    """Test strict type parsing and bounds handling."""

    def test_parse_simple_kind(self):
        value_type = EnvTemplateValueType.parse("string")
        assert value_type.kind == EnvValueKind.STRING
        assert value_type.min_value is None
        assert value_type.max_value is None

    def test_parse_single_arg_means_minimum_only_for_password(self):
        value_type = EnvTemplateValueType.parse("password(16)")
        assert value_type.kind == EnvValueKind.PASSWORD
        assert value_type.min_value == 16
        assert value_type.max_value is None

    def test_parse_single_arg_means_minimum_only_for_int(self):
        value_type = EnvTemplateValueType.parse("int(5)")
        assert value_type.kind == EnvValueKind.INT
        assert value_type.min_value == 5
        assert value_type.max_value is None

    def test_parse_single_arg_means_minimum_only_for_base64(self):
        value_type = EnvTemplateValueType.parse("base64(32)")
        assert value_type.kind == EnvValueKind.BASE64
        assert value_type.min_value == 32
        assert value_type.max_value is None

    def test_parse_with_min_max_bounds(self):
        value_type = EnvTemplateValueType.parse("float(0.1, 2.5)")
        assert value_type.kind == EnvValueKind.FLOAT
        assert value_type.min_value == 0.1
        assert value_type.max_value == 2.5

    def test_parse_with_optional_min(self):
        value_type = EnvTemplateValueType.parse("int(, 100)")
        assert value_type.min_value is None
        assert value_type.max_value == 100

    def test_parse_invalid_kind(self):
        with pytest.raises(ValueError):
            EnvTemplateValueType.parse("unsupported")

    def test_parse_boolean_kind(self):
        value_type = EnvTemplateValueType.parse("boolean")
        assert value_type.kind == EnvValueKind.BOOLEAN
        assert value_type.min_value is None
        assert value_type.max_value is None

    def test_parse_invalid_bounds_for_unbounded_kind(self):
        with pytest.raises(ValueError):
            EnvTemplateValueType.parse("port(1,10)")

    def test_parse_invalid_bound_order(self):
        with pytest.raises(ValidationError):
            EnvTemplateValueType(
                kind=EnvValueKind.INT, min_value=5, max_value=4, raw="int(5,4)"
            )


class TestEnvTemplateVariable:
    """Test variable-level validation for recommended values."""

    def test_memory_recommended_valid(self):
        variable = EnvTemplateVariable(
            key="RAM",
            recommended="256M",
            value_type=EnvTemplateValueType.parse("memory"),
        )
        assert variable.recommended == "256M"

    def test_memory_recommended_invalid(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="RAM",
                recommended="256MB",
                value_type=EnvTemplateValueType.parse("memory"),
            )

    def test_ip_recommended_valid(self):
        variable = EnvTemplateVariable(
            key="IP_ADDR",
            recommended="172.16.0.2",
            value_type=EnvTemplateValueType.parse("ip"),
        )
        assert variable.recommended == "172.16.0.2"

    def test_ip_recommended_invalid(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="IP_ADDR",
                recommended="999.999.999.999",
                value_type=EnvTemplateValueType.parse("ip"),
            )

    def test_port_recommended_out_of_range(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="PORT",
                recommended="70000",
                value_type=EnvTemplateValueType.parse("port"),
            )

    def test_int_recommended_respects_bounds(self):
        variable = EnvTemplateVariable(
            key="RETRIES",
            recommended="3",
            value_type=EnvTemplateValueType.parse("int(1,5)"),
        )
        assert variable.recommended == "3"

    def test_string_recommended_respects_length_bounds(self):
        variable = EnvTemplateVariable(
            key="NAME",
            recommended="abcd",
            value_type=EnvTemplateValueType.parse("string(2,5)"),
        )
        assert variable.recommended == "abcd"

    def test_string_recommended_length_out_of_bounds(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="NAME",
                recommended="abcdef",
                value_type=EnvTemplateValueType.parse("string(2,5)"),
            )

    def test_string_recommended_respects_minimum_only_bound(self):
        variable = EnvTemplateVariable(
            key="NAME",
            recommended="abcd",
            value_type=EnvTemplateValueType.parse("string(4)"),
        )
        assert variable.recommended == "abcd"

    def test_string_recommended_fails_minimum_only_bound(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="NAME",
                recommended="abc",
                value_type=EnvTemplateValueType.parse("string(4)"),
            )

    def test_base64_recommended_respects_length_bounds(self):
        variable = EnvTemplateVariable(
            key="TOKEN",
            recommended="abcdEF12+/==",
            value_type=EnvTemplateValueType.parse("base64(8,16)"),
        )
        assert variable.recommended == "abcdEF12+/=="

    def test_base64_recommended_fails_minimum_length(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="TOKEN",
                recommended="short",
                value_type=EnvTemplateValueType.parse("base64(8,16)"),
            )

    def test_base64urlsafe_recommended_respects_length_bounds(self):
        variable = EnvTemplateVariable(
            key="TOKEN_URLSAFE",
            recommended="abcdEF12-_==",
            value_type=EnvTemplateValueType.parse("base64urlsafe(8,16)"),
        )
        assert variable.recommended == "abcdEF12-_=="

    def test_boolean_recommended_is_normalized_to_lowercase(self):
        variable = EnvTemplateVariable(
            key="FEATURE_FLAG",
            recommended="TrUe",
            value_type=EnvTemplateValueType.parse("boolean"),
        )
        assert variable.recommended == "true"

    def test_boolean_recommended_invalid(self):
        with pytest.raises(ValidationError):
            EnvTemplateVariable(
                key="FEATURE_FLAG",
                recommended="maybe",
                value_type=EnvTemplateValueType.parse("boolean"),
            )

    def test_remember_defaults_false(self):
        variable = EnvTemplateVariable(key="APP_SECRET")
        assert variable.remember is False

    @pytest.mark.parametrize("recommended", ["None", "none", "null", "  None  ", ""])
    def test_recommended_sentinel_values_are_treated_as_unset(self, recommended: str):
        variable = EnvTemplateVariable(
            key="SECRET",
            recommended=recommended,
            value_type=EnvTemplateValueType.parse("passphrase(32)"),
        )
        assert variable.recommended is None


class TestEnvTemplateChoice:
    """Test choice model shape."""

    def test_choice_valid(self):
        choice = EnvTemplateChoice(
            value="always", description="Always restart", default=True
        )
        assert choice.value == "always"
        assert choice.description == "Always restart"
        assert choice.default is True
