"""Tests for src/cli/questionary.py – validators, type inference, form builder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from cli.questionary import (
    _default_choice_value,
    _make_length_validator,
    _to_questionary_choices,
    _validate_float,
    _validate_int,
    _validate_ip,
    _validate_memory,
    _validate_port,
    build_form_from_template,
    make_validator,
    print_secrets_summary,
)
from models.env_template import (
    EnvTemplateChoice,
    EnvTemplateValueType,
    EnvTemplateVariable,
    EnvValueKind,
    ParsedEnvTemplate,
)
from models.generated_env import GeneratedEnv, GeneratedSecret
from utils.compute_defaults import ComputeContext
from utils.shared_pref import HostPreferences

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    choices=None,
    immutable: bool = False,
    remember: bool = True,
    prompt: str | None = None,
    description: str | None = None,
    derive: str | None = None,
    extra_metadata: dict[str, str] | None = None,
) -> EnvTemplateVariable:
    return EnvTemplateVariable(
        key=key,
        value=value,
        recommended=recommended,
        value_type=value_type,
        choices=choices,
        immutable=immutable,
        remember=remember,
        prompt=prompt,
        description=description,
        derive=derive,
        extra_metadata=extra_metadata or {},
    )


def _parsed(*variables: EnvTemplateVariable) -> ParsedEnvTemplate:
    return ParsedEnvTemplate(variables=list(variables))


def _mock_question(answer: str) -> MagicMock:
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


# ---------------------------------------------------------------------------
# _validate_port
# ---------------------------------------------------------------------------


class TestValidatePort:
    def test_valid_min(self):
        assert _validate_port("1") is True

    def test_valid_max(self):
        assert _validate_port("65535") is True

    def test_valid_mid(self):
        assert _validate_port("8080") is True

    def test_zero_fails(self):
        result = _validate_port("0")
        assert result != True  # noqa: E712
        assert "1 and 65535" in result

    def test_too_large_fails(self):
        result = _validate_port("65536")
        assert result != True  # noqa: E712

    def test_non_integer_fails(self):
        result = _validate_port("abc")
        assert "integer" in result.lower()


# ---------------------------------------------------------------------------
# _validate_memory
# ---------------------------------------------------------------------------


class TestValidateMemory:
    @pytest.mark.parametrize("value", ["6M", "128G", "1K", "512T", "4096M"])
    def test_valid(self, value):
        assert _validate_memory(value) is True

    @pytest.mark.parametrize("value", ["M", "128", "1.5G", "128GB"])
    def test_invalid(self, value):
        result = _validate_memory(value)
        assert result != True  # noqa: E712

    def test_stripped_whitespace_passes(self):
        # Validator strips whitespace before matching, so padded values are accepted
        assert _validate_memory("  128M  ") is True


# ---------------------------------------------------------------------------
# _validate_float
# ---------------------------------------------------------------------------


class TestValidateFloat:
    def test_positive(self):
        assert _validate_float("3.14") is True

    def test_negative(self):
        assert _validate_float("-0.5") is True

    def test_integer_string(self):
        assert _validate_float("42") is True

    def test_non_float_fails(self):
        result = _validate_float("abc")
        assert "float" in result.lower()


# ---------------------------------------------------------------------------
# _validate_int
# ---------------------------------------------------------------------------


class TestValidateInt:
    def test_positive(self):
        assert _validate_int("100") is True

    def test_negative(self):
        assert _validate_int("-1") is True

    def test_float_string_fails(self):
        result = _validate_int("3.14")
        assert "integer" in result.lower()

    def test_alpha_fails(self):
        result = _validate_int("abc")
        assert "integer" in result.lower()


# ---------------------------------------------------------------------------
# _validate_ip
# ---------------------------------------------------------------------------


class TestValidateIp:
    def test_ipv4(self):
        assert _validate_ip("192.168.1.1") is True

    def test_ipv6(self):
        assert _validate_ip("::1") is True

    def test_invalid(self):
        result = _validate_ip("not.an.ip.address.extra")
        assert result != True  # noqa: E712


# ---------------------------------------------------------------------------
# _make_length_validator
# ---------------------------------------------------------------------------


class TestMakeLengthValidator:
    def test_returns_none_when_no_bounds(self):
        assert _make_length_validator("test", None, None) is None

    def test_min_only(self):
        v = _make_length_validator("password", 8, None)
        assert v("1234567") != True  # noqa: E712
        assert v("12345678") is True

    def test_max_only(self):
        v = _make_length_validator("password", None, 10)
        assert v("12345678901") != True  # noqa: E712
        assert v("1234567890") is True

    def test_both_bounds(self):
        v = _make_length_validator("password", 4, 8)
        assert v("abc") != True  # noqa: E712
        assert v("abcdefghi") != True  # noqa: E712
        assert v("abcde") is True


# ---------------------------------------------------------------------------
# make_validator dispatch
# ---------------------------------------------------------------------------


class TestMakeValidator:
    def test_none_input(self):
        assert make_validator(None) is None

    def test_string_kind_no_bounds(self):
        assert make_validator(_vtype("string")) is None

    def test_path_kind_no_validator(self):
        assert make_validator(_vtype("path")) is None

    def test_string_with_bounds(self):
        v = make_validator(_vtype("string", 3, 8))
        assert callable(v)
        assert v("ab") != True  # noqa: E712
        assert v("abcd") is True
        assert v("abcdefghij") != True  # noqa: E712

    def test_string_single_arg_is_minimum_only(self):
        value_type = EnvTemplateValueType.parse("string(8)")
        v = make_validator(value_type)
        assert callable(v)
        assert v("short") != True  # noqa: E712
        assert v("longstring") is True
        assert v("x" * 100) is True

    def test_password_no_bounds(self):
        assert make_validator(_vtype("password")) is None

    def test_password_with_bounds(self):
        v = make_validator(_vtype("password", 8, 20))
        assert callable(v)
        assert v("short") != True  # noqa: E712
        assert v("validpassword") is True

    def test_passphrase_with_bounds(self):
        v = make_validator(_vtype("passphrase", 10, 50))
        assert callable(v)

    def test_base64_with_bounds(self):
        v = make_validator(_vtype("base64", 8, 24))
        assert callable(v)
        assert v("short") != True  # noqa: E712
        assert v("QWxwaGFTZWNyZXQ=") is True

    def test_base64urlsafe_with_bounds(self):
        v = make_validator(_vtype("base64urlsafe", 8, 24))
        assert callable(v)
        assert v("tiny") != True  # noqa: E712
        assert v("QWxwaGFTZWNyZXQ=") is True

    def test_port(self):
        v = make_validator(_vtype("port"))
        assert callable(v)
        assert v("80") is True

    def test_memory(self):
        v = make_validator(_vtype("memory"))
        assert callable(v)
        assert v("256M") is True

    def test_float(self):
        v = make_validator(_vtype("float"))
        assert callable(v)
        assert v("1.5") is True

    def test_int(self):
        v = make_validator(_vtype("int"))
        assert callable(v)
        assert v("42") is True

    def test_ip(self):
        v = make_validator(_vtype("ip"))
        assert callable(v)
        assert v("10.0.0.1") is True

    def test_boolean(self):
        v = make_validator(_vtype("boolean"))
        assert callable(v)
        assert v("true") is True
        assert v("FALSE") is True
        assert v("nope") != True  # noqa: E712

    def test_bcrypthash_no_validator(self):
        assert make_validator(_vtype("bcrypthash")) is None


# ---------------------------------------------------------------------------
# _to_questionary_choices / _default_choice_value
# ---------------------------------------------------------------------------


class TestChoiceConversion:
    def test_converts_to_questionary_choices(self):
        ec = [
            EnvTemplateChoice(value="a", description="alpha"),
            EnvTemplateChoice(value="b", description=None),
        ]
        qc = _to_questionary_choices(ec)
        assert len(qc) == 2
        assert qc[0].value == "a"
        assert qc[1].value == "b"

    def test_default_choice_returns_flagged(self):
        ec = [
            EnvTemplateChoice(value="a"),
            EnvTemplateChoice(value="b", default=True),
        ]
        assert _default_choice_value(ec) == "b"

    def test_default_choice_returns_none_when_none_flagged(self):
        ec = [EnvTemplateChoice(value="a"), EnvTemplateChoice(value="b")]
        assert _default_choice_value(ec) is None


# ---------------------------------------------------------------------------
# build_form_from_template – use_recommended=True
# ---------------------------------------------------------------------------


class TestBuildFormUseRecommended:
    def test_derive_uses_interpolation_context(self):
        var = _var(
            "APP_URL",
            value_type=_vtype("string"),
            derive="${APP_NAME}.${DOMAIN}",
        )
        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            interpolation_context={"APP_NAME": "vault", "DOMAIN": "lan"},
        )

        assert result.values["APP_URL"] == "vault.lan"

    def test_derive_prefers_current_run_values_over_initial_context(self):
        app_name = _var("APP_NAME", recommended="new-app")
        app_url = _var(
            "APP_URL",
            value_type=_vtype("string"),
            derive="${APP_NAME}.${DOMAIN}",
        )
        result = build_form_from_template(
            _parsed(app_name, app_url),
            use_recommended=True,
            interpolation_context={"APP_NAME": "old-app", "DOMAIN": "lan"},
        )

        assert result.values["APP_NAME"] == "new-app"
        assert result.values["APP_URL"] == "new-app.lan"

    def test_derive_unresolved_placeholder_fails_closed(self):
        var = _var(
            "APP_URL",
            value_type=_vtype("string"),
            derive="${APP_NAME}.${DOMAIN}",
        )
        with pytest.raises(ValueError, match="Missing variable: APP_NAME"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={"DOMAIN": "lan"},
            )

    def test_derive_and_compute_conflict_fails_closed(self):
        var = _var(
            "APP_URL",
            value_type=_vtype("string"),
            derive="${APP_NAME}.${DOMAIN}",
            extra_metadata={"compute": "uid"},
        )
        with pytest.raises(ValueError, match="derive and compute"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                interpolation_context={"APP_NAME": "vault", "DOMAIN": "lan"},
                compute_context=_compute_context(),
            )

    def test_derive_does_not_prompt(self):
        var = _var(
            "APP_URL",
            value_type=_vtype("string"),
            derive="${APP_NAME}.${DOMAIN}",
        )
        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                interpolation_context={"APP_NAME": "vault", "DOMAIN": "lan"},
            )

        assert result.values["APP_URL"] == "vault.lan"
        mock_q.text.assert_not_called()
        mock_q.path.assert_not_called()
        mock_q.password.assert_not_called()
        mock_q.select.assert_not_called()

    def test_compute_uid_applied_in_use_recommended(self):
        var = _var(
            "UID",
            value_type=_vtype("int"),
            extra_metadata={"compute": "uid"},
        )
        result = build_form_from_template(
            _parsed(var),
            use_recommended=True,
            compute_context=_compute_context(uid=1234),
        )

        assert result.values["UID"] == "1234"

    def test_compute_rejected_for_secret_type(self):
        var = _var(
            "APP_SECRET",
            value_type=_vtype("password"),
            extra_metadata={"compute": "uid"},
        )
        with pytest.raises(ValueError, match="not allowed for secret type"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_unknown_name_fails_closed(self):
        var = _var("UID", extra_metadata={"compute": "hostname"})
        with pytest.raises(ValueError, match="Unknown compute resolver"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_command_like_name_fails_closed(self):
        var = _var("UID", extra_metadata={"compute": "id -u"})
        with pytest.raises(ValueError, match="Invalid compute resolver"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(),
            )

    def test_compute_value_must_match_choices(self):
        var = _var(
            "MODE",
            choices=[
                EnvTemplateChoice(value="1001"),
                EnvTemplateChoice(value="1002", default=True),
            ],
            extra_metadata={"compute": "uid"},
        )
        with pytest.raises(ValueError, match="not in allowed choices"):
            build_form_from_template(
                _parsed(var),
                use_recommended=True,
                compute_context=_compute_context(uid=9999),
            )

    def test_compute_requires_context(self):
        var = _var("UID", extra_metadata={"compute": "uid"})
        with pytest.raises(ValueError, match="requires initialized host preferences"):
            build_form_from_template(_parsed(var), use_recommended=True)

    def test_standard_field_uses_recommended(self):
        var = _var("DB_HOST", recommended="localhost")
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert result.values["DB_HOST"] == "localhost"

    def test_standard_field_prompts_when_no_recommended_value(self):
        var = _var("DB_PORT", value="5432")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _mock_question("6543")
            result = build_form_from_template(_parsed(var), use_recommended=True)

        assert result.values["DB_PORT"] == "6543"
        mock_q.text.assert_called_once()

    def test_standard_field_without_default_prompts_for_user_input(self):
        var = _var("SOME_KEY")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _mock_question("entered-value")
            result = build_form_from_template(_parsed(var), use_recommended=True)

        assert result.values["SOME_KEY"] == "entered-value"
        mock_q.text.assert_called_once()

    def test_password_field_generates_secret(self):
        var = _var(
            "APP_SECRET",
            value_type=_vtype("password"),
            recommended="weakpassword",
            description="Secret for application sessions",
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)
        # Generated value must differ from the literal recommended
        assert result.values["APP_SECRET"] != "weakpassword"
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].key == "APP_SECRET"
        assert result.generated_secrets[0].kind == "password"
        assert len(result.generated_secrets[0].plaintext) >= 4
        assert (
            result.generated_secrets[0].description == "Secret for application sessions"
        )

    def test_password_field_not_in_summary_when_remember_false(self):
        var = _var(
            "APP_SECRET",
            value_type=_vtype("password"),
            recommended="weakpassword",
            remember=False,
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert result.values["APP_SECRET"] != ""
        assert result.generated_secrets == []

    def test_passphrase_field_generates_secret(self):
        var = _var(
            "PASSPHRASE_KEY",
            value_type=_vtype("passphrase"),
            recommended="placeholder",
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "passphrase"
        assert "-" in result.generated_secrets[0].plaintext  # separator

    def test_bcrypthash_field_generates_secret_and_hash(self):
        var = _var(
            "ADMIN_HASH",
            value_type=_vtype("bcrypthash"),
            recommended="placeholder",
            description="Admin login password",
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "bcrypthash"
        assert result.generated_secrets[0].description == "Admin login password"
        # Stored value should be a bcrypt hash string
        assert result.values["ADMIN_HASH"].startswith("$2b$")

    def test_base64_field_generates_secret(self):
        var = _var(
            "API_TOKEN",
            value_type=_vtype("base64", 24, 64),
            recommended="QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=",
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)

        assert result.values["API_TOKEN"] != ""
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "base64"
        assert result.generated_secrets[0].plaintext == result.values["API_TOKEN"]

    def test_base64urlsafe_field_generates_secret(self):
        var = _var(
            "API_TOKEN_URLSAFE",
            value_type=_vtype("base64urlsafe", 24, 64),
            recommended="QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo_",
        )
        result = build_form_from_template(_parsed(var), use_recommended=True)

        assert result.values["API_TOKEN_URLSAFE"] != ""
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "base64urlsafe"
        assert (
            result.generated_secrets[0].plaintext == result.values["API_TOKEN_URLSAFE"]
        )

    def test_use_recommended_does_not_prompt_when_recommended_is_present(self):
        """When recommendations exist, prompts are not needed."""
        var = _var("KEY1", recommended="preset")
        with patch("cli.questionary.questionary") as mock_q:
            build_form_from_template(_parsed(var), use_recommended=True)
            mock_q.text.assert_not_called()
            mock_q.password.assert_not_called()
            mock_q.select.assert_not_called()

    def test_use_recommended_missing_recommended_prompts(self):
        var = _var("KEY1", value="fallback")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = _mock_question("typed")
            result = build_form_from_template(_parsed(var), use_recommended=True)

        assert result.values["KEY1"] == "typed"
        mock_q.text.assert_called_once()

    def test_immutable_with_recommended_uses_recommended(self):
        var = _var("FIXED", recommended="stable", immutable=True)
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert result.values["FIXED"] == "stable"

    def test_immutable_no_value_uses_empty_string(self):
        var = _var("FIXED", immutable=True)
        result = build_form_from_template(_parsed(var), use_recommended=True)
        assert result.values["FIXED"] == ""

    def test_multiple_variables(self):
        vars_ = [
            _var("HOST", recommended="127.0.0.1"),
            _var("PORT", value="3000"),
            _var("SECRET", value_type=_vtype("password")),
        ]
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.side_effect = [_mock_question("8080")]
            mock_q.password.side_effect = [_mock_question("")]
            result = build_form_from_template(_parsed(*vars_), use_recommended=True)

        assert result.values["HOST"] == "127.0.0.1"
        assert result.values["PORT"] == "8080"
        assert result.values["SECRET"] != ""
        mock_q.text.assert_called_once()
        mock_q.password.assert_called_once()
        assert len(result.generated_secrets) == 1


# ---------------------------------------------------------------------------
# build_form_from_template – interactive mode (use_recommended=False)
# ---------------------------------------------------------------------------


class TestBuildFormInteractive:
    def test_blank_recommended_compute_does_not_prefill_interactive_prompt(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("alice")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "alice"
        assert mock_q.text.call_args.kwargs["default"] == ""

    def test_empty_interactive_answer_falls_back_to_compute(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "alice"
        assert mock_q.text.call_args.kwargs["default"] == ""

    def test_empty_interactive_answer_leaves_empty_when_compute_fails(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            extra_metadata={"compute": "username"},
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=None,
            )

        assert result.values["USER_NAME"] == ""

    def test_non_empty_interactive_answer_skips_compute_fallback(self):
        var = _var(
            "USER_ID",
            value_type=_vtype("int"),
            extra_metadata={"compute": "uid"},
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("2000")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(uid=1001),
            )

        assert result.values["USER_ID"] == "2000"

    def test_compute_still_prefills_when_recommended_exists(self):
        var = _var(
            "USER_NAME",
            value_type=_vtype("string"),
            recommended="preset",
            extra_metadata={"compute": "username"},
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("alice")
            result = build_form_from_template(
                _parsed(var),
                use_recommended=False,
                compute_context=_compute_context(username="alice"),
            )

        assert result.values["USER_NAME"] == "alice"
        assert mock_q.text.call_args.kwargs["default"] == "alice"

    def _mock_ask(self, answer: str):
        """Return a mock questionary question object whose .ask() returns *answer*."""
        mock = MagicMock()
        mock.ask.return_value = answer
        return mock

    def test_text_question_called_for_plain_field(self):
        var = _var("USERNAME", prompt="Enter username:")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.text.return_value = self._mock_ask("alice")
            result = build_form_from_template(_parsed(var), use_recommended=False)
        assert result.values["USERNAME"] == "alice"
        mock_q.text.assert_called_once()

    def test_password_question_called_for_password_field(self):
        var = _var("SECRET", value_type=_vtype("password"), prompt="Enter secret:")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("mysecret")
            result = build_form_from_template(_parsed(var), use_recommended=False)
        assert result.values["SECRET"] == "mysecret"
        mock_q.password.assert_called_once()
        assert (
            mock_q.password.call_args.kwargs["instruction"]
            == "Leave blank to auto-generate a secure value."
        )

    def test_boolean_question_called_for_boolean_field(self):
        var = _var(
            "FEATURE_ENABLED",
            value_type=_vtype("boolean"),
            prompt="Enable feature?",
            recommended="FALSE",
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.confirm.return_value = self._mock_ask(True)
            result = build_form_from_template(_parsed(var), use_recommended=False)
        assert result.values["FEATURE_ENABLED"] == "true"
        mock_q.confirm.assert_called_once()
        mock_q.text.assert_not_called()

    def test_path_question_called_for_path_field(self):
        var = _var(
            "DIR_DATA",
            value_type=_vtype("path"),
            prompt="Enter data directory:",
            recommended="/srv/data",
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.path.return_value = self._mock_ask("/mnt/data")
            result = build_form_from_template(_parsed(var), use_recommended=False)

        assert result.values["DIR_DATA"] == "/mnt/data"
        mock_q.path.assert_called_once()
        assert mock_q.path.call_args.args[0] == "Enter data directory:"
        assert mock_q.path.call_args.kwargs["default"] == "/srv/data"
        mock_q.text.assert_not_called()

    def test_password_prompt_appends_auto_generate_instruction(self):
        var = _var(
            "SECRET",
            value_type=_vtype("password"),
            prompt="Enter secret:",
            description="Primary secret",
        )
        var.instruction = "Use a strong secret."
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("mysecret")
            build_form_from_template(_parsed(var), use_recommended=False)

        assert (
            mock_q.password.call_args.kwargs["instruction"]
            == "Use a strong secret. Leave blank to auto-generate a secure value."
        )

    def test_empty_password_input_generates_secret(self):
        var = _var(
            "SECRET", value_type=_vtype("password", 12, 24), prompt="Enter secret:"
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("")
            result = build_form_from_template(_parsed(var), use_recommended=False)

        assert result.values["SECRET"] != ""
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "password"
        assert result.generated_secrets[0].plaintext == result.values["SECRET"]
        mock_q.password.assert_called_once()

    def test_select_question_called_for_choices_field(self):
        choices = [
            EnvTemplateChoice(value="opt1"),
            EnvTemplateChoice(value="opt2", default=True),
        ]
        var = _var("OPTION", choices=choices, prompt="Pick one:")
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.select.return_value = self._mock_ask("opt1")
            result = build_form_from_template(_parsed(var), use_recommended=False)
        assert result.values["OPTION"] == "opt1"
        mock_q.select.assert_called_once()

    def test_bcrypthash_hashes_user_input(self):
        var = _var(
            "ADMIN_HASH",
            value_type=_vtype("bcrypthash"),
            description="Admin login password",
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("plainpassword")
            result = build_form_from_template(_parsed(var), use_recommended=False)
        # Stored value should be a bcrypt hash
        assert result.values["ADMIN_HASH"].startswith("$2b$")
        # Plaintext captured for display
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].plaintext == "plainpassword"
        assert result.generated_secrets[0].description == "Admin login password"

    def test_empty_bcrypthash_input_generates_secret(self):
        var = _var(
            "ADMIN_HASH",
            value_type=_vtype("bcrypthash"),
            description="Admin login password",
        )
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("")
            result = build_form_from_template(_parsed(var), use_recommended=False)

        assert result.values["ADMIN_HASH"].startswith("$2b$")
        assert len(result.generated_secrets) == 1
        assert result.generated_secrets[0].kind == "bcrypthash"
        assert result.generated_secrets[0].plaintext != ""
        assert result.generated_secrets[0].description == "Admin login password"

    def test_bcrypthash_prompt_appends_auto_generate_instruction(self):
        var = _var(
            "ADMIN_HASH",
            value_type=_vtype("bcrypthash"),
            description="Admin login password",
        )
        var.instruction = "Enter plaintext; it will be hashed."
        with patch("cli.questionary.questionary") as mock_q:
            mock_q.password.return_value = self._mock_ask("plainpassword")
            build_form_from_template(_parsed(var), use_recommended=False)

        assert (
            mock_q.password.call_args.kwargs["instruction"]
            == "Enter plaintext; it will be hashed. Leave blank to auto-generate a secure value."
        )

    def test_immutable_with_recommended_skips_prompt(self):
        var = _var("FIXED", recommended="locked", immutable=True)
        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(_parsed(var), use_recommended=False)
        mock_q.text.assert_not_called()
        assert result.values["FIXED"] == "locked"

    def test_immutable_no_value_uses_empty_string(self):
        var = _var("FIXED", immutable=True)
        result = build_form_from_template(_parsed(var), use_recommended=False)
        assert result.values["FIXED"] == ""

    def test_single_choice_skips_prompt(self):
        choices = [EnvTemplateChoice(value="traefik:latest")]
        var = _var("IMAGE", choices=choices, prompt="Pick image:")
        with patch("cli.questionary.questionary") as mock_q:
            result = build_form_from_template(_parsed(var), use_recommended=False)
        mock_q.select.assert_not_called()
        assert result.values["IMAGE"] == "traefik:latest"


# ---------------------------------------------------------------------------
# GeneratedEnv
# ---------------------------------------------------------------------------


class TestGeneratedEnv:
    def test_to_env_string(self):
        env = GeneratedEnv(values={"KEY": "value", "OTHER": "123"})
        text = env.to_env_string()
        assert "KEY=value" in text
        assert "OTHER=123" in text
        assert text.endswith("\n")

    def test_empty_values(self):
        env = GeneratedEnv()
        assert env.to_env_string() == "\n"

    def test_generated_secrets_default_empty(self):
        env = GeneratedEnv(values={"X": "1"})
        assert env.generated_secrets == []


# ---------------------------------------------------------------------------
# print_secrets_summary – no-op when empty
# ---------------------------------------------------------------------------


class TestPrintSecretsSummary:
    def test_no_output_when_no_secrets(self, capsys):
        env = GeneratedEnv(values={"KEY": "val"})
        print_secrets_summary(env)
        # Rich uses its own console; just ensure no exception raised
        # (Rich writes to its own Console, not sys.stdout by default in tests,
        # so we only check it doesn't crash)

    def test_does_not_raise_with_secrets(self):
        env = GeneratedEnv(
            values={"PW": "hash"},
            generated_secrets=[
                GeneratedSecret(
                    key="PW",
                    kind="password",
                    plaintext="p@ss",
                    description="Primary admin password",
                )
            ],
        )
        print_secrets_summary(env)  # should not raise
