"""Extensive derive/compute behavior tests for questionary form builder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cli.questionary import build_form_from_template
from models.env_template import (
    EnvTemplateChoice,
    EnvTemplateValueType,
    EnvTemplateVariable,
    EnvValueKind,
    ParsedEnvTemplate,
)
from utils.compute_defaults import ComputeContext
from utils.shared_pref import HostPreferences


def _vtype(kind: str, min_value=None, max_value=None) -> EnvTemplateValueType:
    return EnvTemplateValueType(
        kind=EnvValueKind(kind), min_value=min_value, max_value=max_value, raw=kind
    )


def _var(
    key: str,
    *,
    value: str = "",
    recommended: str | None = None,
    value_type: EnvTemplateValueType | None = None,
    choices: list[EnvTemplateChoice] | None = None,
    immutable: bool = False,
    derive: str | None = None,
    extra_metadata: dict[str, str] | None = None,
    prompt: str | None = None,
) -> EnvTemplateVariable:
    return EnvTemplateVariable(
        key=key,
        value=value,
        recommended=recommended,
        value_type=value_type,
        choices=choices,
        immutable=immutable,
        derive=derive,
        extra_metadata=extra_metadata or {},
        prompt=prompt,
    )


def _parsed(*variables: EnvTemplateVariable) -> ParsedEnvTemplate:
    return ParsedEnvTemplate(variables=list(variables))


def _ask(answer: str) -> MagicMock:
    mock = MagicMock()
    mock.ask.return_value = answer
    return mock


def _compute_context(
    *,
    username: str = "alice",
    uid: int | None = 1000,
    gid: int | None = 1000,
    docker_gid: int | None = 998,
) -> ComputeContext:
    return ComputeContext(
        host_preferences=HostPreferences(
            username=username,
            uid=uid,
            gid=gid,
            docker_gid=docker_gid,
            architecture="x86_64",
            cpu_count=8,
            ram_mb=16000,
            install_dir="/tmp/homestack",
            install_dir_total_gb=128.0,
        )
    )


class TestDeriveExtensive:
    @pytest.mark.parametrize(
        "expression,context,expected",
        [
            ("${APP}", {"APP": "vault"}, "vault"),
            (
                "https://${APP}.${DOMAIN}",
                {"APP": "vault", "DOMAIN": "lan"},
                "https://vault.lan",
            ),
            ("${MISSING:-fallback}", {}, "fallback"),
            ("cost-$$5", {}, "cost-$5"),
        ],
    )
    def test_derive_expression_variants(self, expression, context, expected):
        var = _var("OUT", derive=expression)
        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            interpolation_context=context,
        )
        assert result.values["OUT"] == expected

    def test_derive_required_token_custom_error(self):
        var = _var("OUT", derive="${APP?APP is required}")
        with pytest.raises(ValueError, match="APP is required"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={},
            )

    def test_derive_uses_extra_metadata_when_field_is_unset(self):
        var = _var("OUT", extra_metadata={"derive": "${APP}.${DOMAIN}"})
        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            interpolation_context={"APP": "vault", "DOMAIN": "lan"},
        )
        assert result.values["OUT"] == "vault.lan"

    def test_derive_type_validation_boolean(self):
        var = _var("FLAG", derive="${APP}", value_type=_vtype("boolean"))
        with pytest.raises(ValueError, match="must be true or false"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={"APP": "vault"},
            )

    def test_derive_choice_validation(self):
        var = _var(
            "MODE",
            derive="${VALUE}",
            choices=[EnvTemplateChoice(value="prod"), EnvTemplateChoice(value="dev")],
        )
        with pytest.raises(ValueError, match="not in allowed choices"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={"VALUE": "staging"},
            )

    def test_derive_is_rejected_for_secret_type(self):
        var = _var("SECRET", derive="${APP}", value_type=_vtype("password"))
        with pytest.raises(ValueError, match="not allowed for secret type"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={"APP": "vault"},
            )

    def test_derive_order_dependency_fails_when_reference_defined_later(self):
        first = _var("APP_URL", derive="${APP_NAME}.lan")
        second = _var("APP_NAME", recommended="vault")

        with pytest.raises(ValueError, match="Missing variable: APP_NAME"):
            build_form_from_template(_parsed(first, second), use_recommended=True)

    def test_derive_order_dependency_succeeds_when_reference_defined_earlier(self):
        first = _var("APP_NAME", recommended="vault")
        second = _var("APP_URL", derive="${APP_NAME}.lan")

        result = build_form_from_template(_parsed(first, second), use_recommended=True)

        assert result.values["APP_NAME"] == "vault"
        assert result.values["APP_URL"] == "vault.lan"

    def test_derive_uses_interactive_answer_from_previous_variable(self):
        name_var = _var("APP_NAME", prompt="App name:")
        url_var = _var("APP_URL", derive="https://${APP_NAME}.lan")

        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.side_effect = [_ask("vault"), _ask("https://vault.lan")]
            result = build_form_from_template(
                _parsed(name_var, url_var),
                use_recommended=False,
                interpolation_context={"APP_NAME": "old"},
            )

        assert result.values["APP_NAME"] == "vault"
        assert result.values["APP_URL"] == "https://vault.lan"
        assert mock_q.text.call_count == 2
        assert mock_q.text.call_args_list[1].kwargs["default"] == "https://vault.lan"

    def test_derive_mutable_prompts_with_derived_default(self):
        var = _var("APP_URL", derive="https://${APP}.lan", value_type=_vtype("string"))

        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _ask("https://custom.lan")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                interpolation_context={"APP": "vault"},
            )

        assert result.values["APP_URL"] == "https://custom.lan"
        assert mock_q.text.call_args.kwargs["default"] == "https://vault.lan"

    def test_derive_immutable_is_auto_applied_without_prompt(self):
        var = _var(
            "APP_URL",
            derive="https://${APP}.lan",
            value_type=_vtype("string"),
            immutable=True,
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                interpolation_context={"APP": "vault"},
            )

        assert result.values["APP_URL"] == "https://vault.lan"
        mock_q.text.assert_not_called()


class TestComputeExtensive:
    def test_compute_overrides_existing_recommended(self):
        var = _var(
            "USER_NAME",
            recommended="preset",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(username="alice"),
        )

        assert result.values["USER_NAME"] == "alice"

    def test_compute_result_validation_boolean(self):
        var = _var(
            "FLAG",
            value_type=_vtype("boolean"),
            extra_metadata={"compute": "username"},
        )
        with pytest.raises(ValueError, match="must be true or false"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(username="alice"),
            )

    def test_compute_result_validation_int_with_monkeypatch(self):
        var = _var(
            "USER_ID", value_type=_vtype("int"), extra_metadata={"compute": "uid"}
        )
        with patch("cli.questionary.resolve_computed_value", return_value="not-an-int"):
            with pytest.raises(ValueError, match="must be a valid integer"):
                build_form_from_template(
                    _parsed(var),
                    use_recommended=True,
                    compute_context=_compute_context(uid=1000),
                )

    def test_compute_immutable_in_interactive_mode_does_not_prompt(self):
        var = _var(
            "UID",
            immutable=True,
            value_type=_vtype("int"),
            extra_metadata={"compute": "uid"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(uid=1234),
            )

        assert result.values["UID"] == "1234"
        mock_q.text.assert_not_called()

    def test_compute_interactive_deferred_with_non_blank_answer_wins(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _ask("manual-name")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "manual-name"

    def test_compute_interactive_deferred_with_blank_answer_uses_compute(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _ask("")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "alice"

    def test_compute_not_deferred_for_choices_and_applies_before_prompt(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            choices=[EnvTemplateChoice(value="alice")],
            extra_metadata={"compute": "username"},
        )
        result = build_form_from_template(
            _parsed(var),
            use_recommended=False,
            compute_context=_compute_context(username="alice"),
        )

        assert result.values["USER_NAME"] == "alice"

    def test_compute_host_ram_total_immutable_no_prompt(self):
        """Test host_ram computes total without prompting."""
        var = _var(
            "HC_HOST_RAM",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(),
            )

        assert result.values["HC_HOST_RAM"] == "16G"
        mock_q.text.assert_not_called()

    def test_compute_host_cpu_total_immutable_no_prompt(self):
        """Test host_cpu computes total without prompting."""
        var = _var(
            "HC_HOST_CPU",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(),
            )

        assert result.values["HC_HOST_CPU"] == "8"
        mock_q.text.assert_not_called()

    def test_compute_host_ram_80pct_immutable_no_prompt(self):
        """Test host_ram_80 computes percentage without prompting."""
        var = _var(
            "RAM_MAX",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram_80"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(),
            )

        # 80% of 16000 MB = 12800 MB
        assert result.values["RAM_MAX"] in ["12G", "12800M"]
        mock_q.text.assert_not_called()

    def test_compute_host_cpu_50pct_immutable_no_prompt(self):
        """Test host_cpu_50 computes percentage without prompting."""
        var = _var(
            "CPU_RESERVE",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu_50"},
        )

        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(),
            )

        # 50% of 8 threads = 4.00
        assert result.values["CPU_RESERVE"] == "4.00"
        mock_q.text.assert_not_called()

    def test_compute_host_ram_total_overrides_recommended(self):
        """Test that host_ram overrides recommended value."""
        var = _var(
            "HC_HOST_RAM",
            recommended="2G",
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        assert result.values["HC_HOST_RAM"] == "16G"

    def test_compute_host_cpu_percent_overrides_recommended(self):
        """Test that host_cpu_80 overrides recommended value."""
        var = _var(
            "CPU_MAX",
            recommended="2.0",
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu_80"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        # 80% of 8 threads = 6.40
        assert result.values["CPU_MAX"] == "6.40"

    def test_compute_host_ram_invalid_percent_rejected(self):
        """Test that invalid percentages are rejected."""
        var = _var(
            "RAM",
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram_150"},
        )

        with pytest.raises(ValueError, match="invalid percent"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_host_ram_multiple_invalid_percentages_rejected(self):
        """Test that multiple over-100 percentage values are all rejected."""
        for invalid_percent in [101, 150, 200, 999]:
            var = _var(
                "RAM",
                value_type=_vtype("string"),
                extra_metadata={"compute": f"host_ram_{invalid_percent}"},
            )

            with pytest.raises(ValueError, match="invalid percent"):
                build_form_from_template(
                    _parsed(var),
                    use_recommended=True,
                    compute_context=_compute_context(),
                )

    def test_compute_host_cpu_multiple_invalid_percentages_rejected(self):
        """Test that multiple over-100 CPU percentage values are all rejected."""
        for invalid_percent in [101, 110, 200, 500]:
            var = _var(
                "CPU",
                value_type=_vtype("string"),
                extra_metadata={"compute": f"host_cpu_{invalid_percent}"},
            )

            with pytest.raises(ValueError, match="invalid percent"):
                build_form_from_template(
                    _parsed(var),
                    use_recommended=True,
                    compute_context=_compute_context(),
                )

    def test_compute_host_ram_non_numeric_suffix_rejected(self):
        """Test that non-numeric suffixes for host_ram are rejected."""
        var = _var(
            "RAM",
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram_invalid"},
        )

        with pytest.raises(ValueError, match="non-numeric suffix"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_host_cpu_non_numeric_suffix_rejected(self):
        """Test that non-numeric suffixes for host_cpu are rejected."""
        var = _var(
            "CPU",
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu_xyz"},
        )

        with pytest.raises(ValueError, match="non-numeric suffix"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_host_ram_boundary_0_percent(self):
        """Test that 0% is valid and resolves to 0M."""
        var = _var(
            "RAM_ZERO",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram_0"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        assert result.values["RAM_ZERO"] == "0M"

    def test_compute_host_ram_boundary_100_percent(self):
        """Test that 100% resolves to total host RAM."""
        var = _var(
            "RAM_FULL",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_ram_100"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        # 100% of 16000 MB = 16000 MB = 16G
        assert result.values["RAM_FULL"] == "16G"

    def test_compute_host_cpu_boundary_0_percent(self):
        """Test that 0% is valid and resolves to 0.00."""
        var = _var(
            "CPU_ZERO",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu_0"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        assert result.values["CPU_ZERO"] == "0.00"

    def test_compute_host_cpu_boundary_100_percent(self):
        """Test that 100% resolves to total host CPU."""
        var = _var(
            "CPU_FULL",
            immutable=True,
            value_type=_vtype("string"),
            extra_metadata={"compute": "host_cpu_100"},
        )

        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(),
        )

        # 100% of 8 threads = 8.00
        assert result.values["CPU_FULL"] == "8.00"


class TestDeriveComputeMixed:
    def test_mixed_compute_then_derive(self):
        computed = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        derived = _var(
            "USER_DIR",
            derive="/home/${USER_NAME}",
            value_type=_vtype("string"),
        )

        result = build_form_from_template(
            _parsed(computed, derived),
            use_recommended=True,
            compute_context=_compute_context(username="alice"),
        )

        assert result.values["USER_NAME"] == "alice"
        assert result.values["USER_DIR"] == "/home/alice"

    def test_mixed_interactive_compute_fallback_then_derive(self):
        computed = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        derived = _var("URL", derive="https://${USER_NAME}.lan")

        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.side_effect = [_ask(""), _ask("https://alice.lan")]
            result = build_form_from_template(
                _parsed(computed, derived),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "alice"
        assert result.values["URL"] == "https://alice.lan"

    def test_mixed_derive_and_compute_on_same_var_fails_closed(self):
        var = _var(
            "OUT",
            derive="${APP_NAME}.lan",
            extra_metadata={"compute": "username"},
        )
        with pytest.raises(
            ValueError, match="derive and compute cannot be used together"
        ):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(username="alice"),
                interpolation_context={"APP_NAME": "vault"},
            )
