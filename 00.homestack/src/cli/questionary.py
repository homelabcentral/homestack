"""Questionary abstraction for interactive CLI prompts driven by env.template metadata.

Public API
----------
- ``ask_text`` / ``ask_password`` / ``ask_path`` / ``ask_confirm`` / ``ask_select``
  – thin wrappers around ``questionary`` primitives that accept optional validators
    and metadata already aligned to ``EnvTemplateVariable`` fields.
- ``make_validator`` – dispatch function that turns an ``EnvTemplateValueType``
  into a ``questionary``-compatible validator callable (or ``None``).
- ``build_form_from_template`` – orchestration function that converts a
  ``ParsedEnvTemplate`` into a ``GeneratedEnv``:
      * interactive mode: asks one prompt per variable using inferred question types.
      * ``use_recommended=True``: skips all prompts; generates fresh secure values
        for password / passphrase / bcrypthash kinds, uses recommended/default for
        everything else.
  Secrets generated during either path are captured in ``GeneratedEnv.generated_secrets``.
- ``print_secrets_summary`` – renders a Rich table of captured secrets with a
  save-it-safely warning.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Callable

import questionary
from models.env_template import (
    EnvTemplateChoice,
    EnvTemplateValueType,
    EnvTemplateVariable,
    EnvValueKind,
    ParsedEnvTemplate,
)
from models.generated_env import GeneratedEnv, GeneratedSecret
from questionary import Choice, Style
from rich.console import Console
from utils.compute_defaults import (
    ComputeContext,
    ComputeResolverError,
    resolve_computed_value,
)
from utils.project_table import ProjectTableBuilder
from utils.secure_values import SecureValueGenerator

_MEMORY_PATTERN = re.compile(r"^[0-9]+[KMGT]$")
_SECRET_KINDS = {
    EnvValueKind.PASSWORD,
    EnvValueKind.PASSPHRASE,
    EnvValueKind.BASE64,
    EnvValueKind.BASE64URLSAFE,
    EnvValueKind.BCRYPTHASH,
}

_console = Console()
_generator = SecureValueGenerator()

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

HOMESTACK_STYLE = Style(
    [
        ("qmark", "fg:#7c6af7 bold"),  # ❯ token before the question
        ("question", "fg:#e2e8f0 bold"),  # question text
        ("answer", "fg:#a3e635 bold"),  # submitted answer
        ("pointer", "fg:#7c6af7 bold"),  # ▶ next to highlighted option
        ("highlighted", "fg:#f0abfc bold"),  # currently focused option
        ("selected", "fg:#a3e635"),  # ticked item in checkbox
        ("separator", "fg:#475569 italic"),  # list separators
        ("instruction", "fg:#64748b italic"),  # (Use arrow keys) hint text
        ("text", "fg:#cbd5e1"),  # miscellaneous text
        ("disabled", "fg:#475569 italic"),  # greyed-out disabled choices
        ("search_success", "noinherit fg:#4ade80 bold"),
        ("search_none", "noinherit fg:#f87171 bold"),
        # autocomplete dropdown — give it a dark bg so text is always readable
        ("completion-menu.completion", "bg:#1e1b2e fg:#cbd5e1"),
        ("completion-menu.completion.current", "bg:#7c6af7 fg:#ffffff bold"),
        ("completion-menu.meta.completion", "bg:#1e1b2e fg:#475569"),
        ("completion-menu.meta.completion.current", "bg:#7c6af7 fg:#e2e8f0"),
    ]
)

# ---------------------------------------------------------------------------
# Primitive wrappers
# ---------------------------------------------------------------------------


def ask_text(
    message: str,
    *,
    instruction: str | None = None,
    default: str = "",
    validate: Callable[[str], bool | str] | None = None,
) -> str:
    """Ask a plain-text question and return the answer."""
    kwargs: dict = {"default": default}
    if instruction:
        kwargs["instruction"] = instruction
    if validate:
        kwargs["validate"] = validate
    result = questionary.text(message, style=HOMESTACK_STYLE, **kwargs).ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def ask_password(
    message: str,
    *,
    instruction: str | None = None,
    validate: Callable[[str], bool | str] | None = None,
) -> str:
    """Ask a password (hidden input) question and return the answer."""
    kwargs: dict = {}
    if instruction:
        kwargs["instruction"] = instruction
    if validate:
        kwargs["validate"] = validate
    result = questionary.password(message, style=HOMESTACK_STYLE, **kwargs).ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def ask_path(
    message: str,
    *,
    instruction: str | None = None,
    default: str = "",
    only_files: bool = False,
) -> str:
    """Ask a file-path question and return the answer."""
    kwargs: dict = {"default": default, "only_files": only_files}
    if instruction:
        kwargs["instruction"] = instruction
    result = questionary.path(message, style=HOMESTACK_STYLE, **kwargs).ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def ask_confirm(
    message: str,
    *,
    instruction: str | None = None,
    default: bool = True,
) -> bool:
    """Ask a yes/no confirmation question and return the answer."""
    kwargs: dict = {"default": default}
    if instruction:
        kwargs["instruction"] = instruction
    result = questionary.confirm(message, style=HOMESTACK_STYLE, **kwargs).ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def ask_select(
    message: str,
    choices: list[Choice | str],
    *,
    instruction: str | None = None,
    default: str | None = None,
) -> str:
    """Ask a select (single-choice) question and return the chosen value."""
    kwargs: dict = {"choices": choices}
    if instruction:
        kwargs["instruction"] = instruction
    if default is not None:
        kwargs["default"] = default
    result = questionary.select(message, style=HOMESTACK_STYLE, **kwargs).ask()
    if result is None:
        raise KeyboardInterrupt
    return result


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _make_length_validator(
    label: str,
    min_length: int | None,
    max_length: int | None,
) -> Callable[[str], bool | str] | None:
    """Return a validator enforcing string-length bounds, or None if no bounds."""
    if min_length is None and max_length is None:
        return None

    def _validate(value: str) -> bool | str:
        length = len(value)
        if min_length is not None and length < min_length:
            return f"{label} must be at least {min_length} characters (got {length})"
        if max_length is not None and length > max_length:
            return f"{label} must be at most {max_length} characters (got {length})"
        return True

    return _validate


def _validate_port(value: str) -> bool | str:
    try:
        port = int(value)
    except ValueError:
        return "Port must be an integer"
    if port < 1 or port > 65535:
        return "Port must be between 1 and 65535"
    return True


def _validate_memory(value: str) -> bool | str:
    if not _MEMORY_PATTERN.fullmatch(value.strip()):
        return "Memory must be a number followed by K, M, G, or T (e.g. 128M, 2G)"
    return True


def _validate_float(value: str) -> bool | str:
    try:
        float(value)
        return True
    except ValueError:
        return "Value must be a valid float (e.g. 3.14)"


def _validate_int(value: str) -> bool | str:
    try:
        int(value)
        return True
    except ValueError:
        return "Value must be a valid integer"


def _validate_ip(value: str) -> bool | str:
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return "Value must be a valid IP address (IPv4 or IPv6)"


def _validate_boolean(value: str) -> bool | str:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        return "Value must be true or false"
    return True


def _normalize_bool(value: str) -> str:
    return "true" if value.strip().lower() == "true" else "false"


def _bool_default(var: EnvTemplateVariable) -> bool:
    source = var.recommended if var.recommended else var.value
    return source.strip().lower() == "true"


def make_validator(
    value_type: EnvTemplateValueType | None,
) -> Callable[[str], bool | str] | None:
    """Dispatch the correct validator callable for the given ``EnvTemplateValueType``.

    Returns ``None`` when no validation applies (e.g. plain string, unknown type).
    """
    if value_type is None:
        return None

    kind = value_type.kind

    if kind in {
        EnvValueKind.STRING,
        EnvValueKind.PASSWORD,
        EnvValueKind.PASSPHRASE,
        EnvValueKind.BASE64,
        EnvValueKind.BASE64URLSAFE,
    }:
        min_len = (
            int(value_type.min_value) if value_type.min_value is not None else None
        )
        max_len = (
            int(value_type.max_value) if value_type.max_value is not None else None
        )
        return _make_length_validator(kind, min_len, max_len)

    if kind == EnvValueKind.PORT:
        return _validate_port

    if kind == EnvValueKind.MEMORY:
        return _validate_memory

    if kind == EnvValueKind.FLOAT:
        return _validate_float

    if kind == EnvValueKind.INT:
        return _validate_int

    if kind == EnvValueKind.IP:
        return _validate_ip

    if kind == EnvValueKind.BOOLEAN:
        return _validate_boolean

    return None


# ---------------------------------------------------------------------------
# Choice conversion
# ---------------------------------------------------------------------------


def _to_questionary_choices(choices: list[EnvTemplateChoice]) -> list[Choice]:
    """Convert ``EnvTemplateChoice`` objects to ``questionary.Choice`` instances."""
    result: list[Choice] = []
    for choice in choices:
        result.append(
            Choice(
                title=choice.value,
                value=choice.value,
                description=choice.description or "",
            )
        )
    return result


def _default_choice_value(choices: list[EnvTemplateChoice]) -> str | None:
    """Return the value of the first choice flagged as default, or None."""
    for choice in choices:
        if choice.default:
            return choice.value
    return None


# ---------------------------------------------------------------------------
# Secure generation helpers
# ---------------------------------------------------------------------------


def _generate_secret_for_variable(
    var: EnvTemplateVariable,
) -> tuple[str, GeneratedSecret]:
    """Generate a fresh secure value for a secret variable.

    Returns ``(env_value, GeneratedSecret)`` where *env_value* is what should be
    written to the .env file and *GeneratedSecret* carries the plaintext for display.
    """
    kind = EnvValueKind(var.value_type.kind) if var.value_type else None
    min_val = (
        int(var.value_type.min_value)
        if (var.value_type and var.value_type.min_value is not None)
        else None
    )
    max_val = (
        int(var.value_type.max_value)
        if (var.value_type and var.value_type.max_value is not None)
        else None
    )

    if kind == EnvValueKind.PASSWORD:
        plaintext = _generator.generate_password(min_val, max_val)
        return plaintext, GeneratedSecret(
            key=var.key,
            kind="password",
            plaintext=plaintext,
            description=var.description,
        )

    if kind == EnvValueKind.PASSPHRASE:
        plaintext = _generator.generate_passphrase(min_val, max_val)
        return plaintext, GeneratedSecret(
            key=var.key,
            kind="passphrase",
            plaintext=plaintext,
            description=var.description,
        )

    if kind == EnvValueKind.BASE64:
        plaintext = _generator.generate_base64(min_val, max_val)
        return plaintext, GeneratedSecret(
            key=var.key,
            kind="base64",
            plaintext=plaintext,
            description=var.description,
        )

    if kind == EnvValueKind.BASE64URLSAFE:
        plaintext = _generator.generate_base64_urlsafe(min_val, max_val)
        return plaintext, GeneratedSecret(
            key=var.key,
            kind="base64urlsafe",
            plaintext=plaintext,
            description=var.description,
        )

    if kind == EnvValueKind.BCRYPTHASH:
        result = _generator.generate_bcrypthash(min_length=min_val, max_length=max_val)
        return result.bcrypt_hash, GeneratedSecret(
            key=var.key,
            kind="bcrypthash",
            plaintext=result.password,
            description=var.description,
        )

    raise ValueError(f"Cannot generate secret for kind: {kind}")


def _resolve_non_secret_value(var: EnvTemplateVariable) -> str:
    """Resolve the final value for a non-secret variable without prompting."""
    return var.recommended if var.recommended else var.value


def _resolve_recommended_value(
    var: EnvTemplateVariable,
) -> tuple[str, GeneratedSecret | None]:
    """Resolve one variable for ``use_recommended=True`` flows."""
    kind = EnvValueKind(var.value_type.kind) if var.value_type else None
    if kind in _SECRET_KINDS:
        return _generate_secret_for_variable(var)
    return _resolve_non_secret_value(var), None


def _apply_compute_default(
    var: EnvTemplateVariable,
    compute_context: ComputeContext | None,
) -> EnvTemplateVariable:
    """Return a copy of *var* with ``recommended`` overridden by ``compute``.

    This is intentionally fail-closed for safety: any invalid or unsupported
    compute configuration raises ``ValueError`` and aborts env generation.
    """
    resolver_name = (var.extra_metadata.get("compute") or "").strip()
    if not resolver_name:
        return var

    if compute_context is None:
        raise ValueError(
            f"{var.key}: compute resolver requires initialized host preferences"
        )

    kind = EnvValueKind(var.value_type.kind) if var.value_type else None
    if kind in _SECRET_KINDS:
        raise ValueError(
            f"{var.key}: compute is not allowed for secret type '{kind.value}'"
        )

    try:
        resolved_value = resolve_computed_value(resolver_name, compute_context)
    except ComputeResolverError as exc:
        raise ValueError(f"{var.key}: {exc}") from exc

    if var.choices and all(choice.value != resolved_value for choice in var.choices):
        raise ValueError(
            f"{var.key}: computed value '{resolved_value}' is not in allowed choices"
        )

    validator = make_validator(var.value_type)
    if validator is not None:
        validation_result = validator(resolved_value)
        if validation_result is not True:
            raise ValueError(
                f"{var.key}: computed value '{resolved_value}' is invalid: {validation_result}"
            )

    data = var.model_dump()
    data["recommended"] = resolved_value
    return EnvTemplateVariable(**data)


def _allow_empty_secret_input(
    validator: Callable[[str], bool | str] | None,
) -> Callable[[str], bool | str] | None:
    """Allow blank secret input to signal auto-generation while preserving validation otherwise."""
    if validator is None:
        return None

    def _validate(value: str) -> bool | str:
        if value == "":
            return True
        return validator(value)

    return _validate


def _secret_instruction(instruction: str | None) -> str:
    """Return instruction text that advertises blank-input auto generation for secrets."""
    suffix = "Leave blank to auto-generate a secure value."
    if not instruction:
        return suffix
    if suffix in instruction:
        return instruction
    return f"{instruction} {suffix}"


# ---------------------------------------------------------------------------
# Interactive prompt helpers
# ---------------------------------------------------------------------------


def _ask_variable_interactive(
    var: EnvTemplateVariable,
) -> tuple[str, GeneratedSecret | None]:
    """Ask a single interactive question for *var* and return ``(value, secret|None)``.

    For bcrypthash, the user supplies plaintext which is then hashed before
    being stored; the plaintext is captured as a ``GeneratedSecret``.
    """
    message = var.prompt or f"Enter value for {var.key}:"
    instruction = var.instruction
    validator = make_validator(var.value_type)
    kind = EnvValueKind(var.value_type.kind) if var.value_type else None

    # Select
    if var.choices:
        if len(var.choices) == 1:
            return var.choices[0].value, None
        q_choices = _to_questionary_choices(var.choices)
        default_val = _default_choice_value(var.choices)
        answer = ask_select(
            message, q_choices, instruction=instruction, default=default_val
        )
        return answer, None

    # Secret inputs → hidden input, no default shown. Empty input means auto-generate.
    if kind in (
        EnvValueKind.PASSWORD,
        EnvValueKind.PASSPHRASE,
        EnvValueKind.BASE64,
        EnvValueKind.BASE64URLSAFE,
    ):
        answer = ask_password(
            message,
            instruction=_secret_instruction(instruction),
            validate=_allow_empty_secret_input(validator),
        )
        if answer == "":
            return _generate_secret_for_variable(var)
        return answer, None

    # Bcrypthash → prompt for plaintext, hash it, capture secret
    if kind == EnvValueKind.BCRYPTHASH:
        plaintext = ask_password(
            message,
            instruction=_secret_instruction(
                instruction or "(enter plaintext; it will be bcrypt-hashed)"
            ),
        )
        if plaintext == "":
            return _generate_secret_for_variable(var)
        hashed = _generator.generate_bcrypthash(password=plaintext)
        secret = GeneratedSecret(
            key=var.key,
            kind="bcrypthash",
            plaintext=plaintext,
            description=var.description,
        )
        return hashed.bcrypt_hash, secret

    if kind == EnvValueKind.BOOLEAN:
        answer = ask_confirm(
            message, instruction=instruction, default=_bool_default(var)
        )
        return ("true" if answer else "false"), None

    if kind == EnvValueKind.PATH:
        default_val = var.recommended if var.recommended else var.value
        answer = ask_path(message, instruction=instruction, default=default_val)
        return answer, None

    # Default → text
    default_val = var.recommended if var.recommended else var.value
    answer = ask_text(
        message, instruction=instruction, default=default_val, validate=validator
    )
    return answer, None


# ---------------------------------------------------------------------------
# Form builder
# ---------------------------------------------------------------------------


def build_form_from_template(
    parsed: ParsedEnvTemplate,
    *,
    use_recommended: bool = False,
    compute_context: ComputeContext | None = None,
) -> GeneratedEnv:
    """Convert a ``ParsedEnvTemplate`` into a ``GeneratedEnv``.

    Parameters
    ----------
    parsed:
        The parsed env template produced by ``EnvTemplateParser``.
    use_recommended:
        When ``True``, prefer template recommendations. Variables with a
        non-empty ``recommended`` value are auto-filled (secrets still generate
        fresh secure values). Variables without a recommendation are prompted
        interactively unless immutable; immutable variables instead fall back
        to the template ``value`` field when no ``recommended`` value exists.

    Returns
    -------
    GeneratedEnv
        Env values dict plus any captured plaintext secrets.
    """
    values: dict[str, str] = {}
    secrets: list[GeneratedSecret] = []

    for var in parsed.variables:
        effective_var = _apply_compute_default(var, compute_context)

        if use_recommended:
            if effective_var.recommended:
                env_val, secret = _resolve_recommended_value(effective_var)
                values[effective_var.key] = env_val
                if secret is not None and effective_var.remember:
                    secrets.append(secret)
            else:
                if effective_var.immutable:
                    # Immutable: skip prompting, use recommended or value (may be empty string)
                    values[effective_var.key] = (
                        effective_var.recommended
                        if effective_var.recommended
                        else effective_var.value
                    )
                else:
                    env_val, secret = _ask_variable_interactive(effective_var)
                    values[effective_var.key] = env_val
                    if secret is not None and effective_var.remember:
                        secrets.append(secret)
        else:
            if effective_var.immutable:
                # Immutable: skip prompting, use recommended or value (may be empty string)
                values[effective_var.key] = (
                    effective_var.recommended
                    if effective_var.recommended
                    else effective_var.value
                )
            else:
                env_val, secret = _ask_variable_interactive(effective_var)
                values[effective_var.key] = env_val
                if secret is not None and effective_var.remember:
                    secrets.append(secret)

    return GeneratedEnv(values=values, generated_secrets=secrets)


# ---------------------------------------------------------------------------
# Rich summary
# ---------------------------------------------------------------------------


def print_secrets_summary(generated: GeneratedEnv) -> None:
    """Print a Rich table of generated secrets with a save-it-safely warning.

    Does nothing if there are no generated secrets.
    """
    if not generated.generated_secrets:
        return

    _console.print()
    _console.print(
        "[bold yellow]⚠  SAVE THESE SECRETS IN A SAFE PLACE.[/bold yellow]  "
        "They will not be shown again.",
    )
    _console.print()

    _console.print(
        ProjectTableBuilder.build_secrets_summary(generated.generated_secrets)
    )
    _console.print()
