"""Strict compliance checks for project ``.env.template`` inline metadata.

These tests intentionally fail hard with actionable remediation guidance when
project templates deviate from the parsing contract used by homestack.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest
from parsers import EnvTemplateParser

# Inline metadata is optional. When type is omitted, runtime defaults to string.
REQUIRED_INLINE_KEYS: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComplianceViolation:
    line: int
    code: str
    message: str
    fix: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _projects_payload() -> list[dict[str, object]]:
    projects_path = _repo_root() / "00.api" / "v1" / "projects.json"
    return json.loads(projects_path.read_text(encoding="utf-8"))


def _project_template_cases() -> list[tuple[str, Path]]:
    root = _repo_root()
    cases: list[tuple[str, Path]] = []
    for row in _projects_payload():
        project_name = str(row.get("project_name", "<unknown project>"))
        dir_name = str(row.get("dir_name", "")).strip()
        env_name = str(row.get("env", "")).strip()

        if not dir_name:
            continue

        template_path = root / dir_name / (env_name or ".env.template")
        cases.append((project_name, template_path))
    return cases


def _case_id(case: tuple[str, Path]) -> str:
    project_name, template_path = case
    return f"{project_name}:{template_path.parent.name}"


def _split_inline_fragments(comment: str) -> list[str]:
    return [
        fragment.strip()
        for fragment in EnvTemplateParser._split_outside_backticks(comment)
        if fragment.strip()
    ]


def _inline_fragments(rhs: str) -> list[str]:
    if "#" not in rhs:
        return []
    _, comment = rhs.split("#", 1)
    return _split_inline_fragments(comment.strip())


def _iter_template_variable_lines(template_path: Path):
    in_metadata = False
    for line_number, line in enumerate(
        template_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if stripped == "# METADATA --- START":
            in_metadata = True
            continue
        if stripped == "# METADATA --- END":
            in_metadata = False
            continue
        if in_metadata or not stripped or stripped.startswith("#"):
            continue
        yield line_number, line


def _validate_inline_contract(template_path: Path) -> list[ComplianceViolation]:
    violations: list[ComplianceViolation] = []

    for line_number, line in _iter_template_variable_lines(template_path):
        if "=" not in line:
            violations.append(
                ComplianceViolation(
                    line=line_number,
                    code="MALFORMED_VARIABLE_LINE",
                    message="Variable line is missing '=' delimiter.",
                    fix="Use KEY=value syntax before any inline metadata comment.",
                )
            )
            continue

        key_part, rhs = line.split("=", 1)
        key = key_part.strip()
        if not key:
            violations.append(
                ComplianceViolation(
                    line=line_number,
                    code="EMPTY_VARIABLE_KEY",
                    message="Variable key is empty.",
                    fix="Set a non-empty variable key, e.g. APP_PORT= # type=port | prompt=...",
                )
            )
            continue

        fragments = _inline_fragments(rhs)
        parsed_keys: list[str] = []

        for fragment in fragments:
            if "=" not in fragment:
                violations.append(
                    ComplianceViolation(
                        line=line_number,
                        code="MALFORMED_INLINE_FRAGMENT",
                        message=(
                            f"Inline metadata fragment '{fragment}' does not use key=value format."
                        ),
                        fix=(
                            "Rewrite inline metadata as pipe-delimited key=value parts, "
                            "for example: # type=string | prompt=Enter value"
                        ),
                    )
                )
                continue

            raw_key, _raw_value = fragment.split("=", 1)
            key_name = raw_key.strip().lower()
            if not key_name:
                violations.append(
                    ComplianceViolation(
                        line=line_number,
                        code="EMPTY_INLINE_KEY",
                        message="Inline metadata has an empty key name.",
                        fix="Provide an inline key name, e.g. type=string instead of =string.",
                    )
                )
                continue
            parsed_keys.append(key_name)

        counts = Counter(parsed_keys)
        for duplicated_key, count in sorted(counts.items()):
            if count <= 1:
                continue
            violations.append(
                ComplianceViolation(
                    line=line_number,
                    code="DUPLICATE_INLINE_KEY",
                    message=(
                        f"Inline metadata key '{duplicated_key}' appears {count} times "
                        f"for variable '{key}'."
                    ),
                    fix=(
                        f"Keep only one '{duplicated_key}=...' fragment on this line; "
                        "remove duplicate occurrences."
                    ),
                )
            )

        parsed_set = set(parsed_keys)
        missing_required = [
            required_key
            for required_key in REQUIRED_INLINE_KEYS
            if required_key not in parsed_set
        ]
        if missing_required:
            readable = ", ".join(missing_required)
            fix_parts = [f"{name}=..." for name in missing_required]
            violations.append(
                ComplianceViolation(
                    line=line_number,
                    code="MISSING_REQUIRED_INLINE_KEYS",
                    message=(
                        f"Variable '{key}' is missing required inline key(s): {readable}."
                    ),
                    fix=(
                        "Add required metadata fragments to this variable line: "
                        + " | ".join(fix_parts)
                    ),
                )
            )

    return violations


def _warn_fix_hint(field: str, message: str) -> str:
    if field == "inline_metadata":
        return "Use key=value fragments separated by '|', for example: # type=string | prompt=..."
    if field == "type":
        return "Use a valid type syntax such as type=string, type=port, or type=int(1,65535)."
    if field == "choices":
        return "Wrap choices in brackets, e.g. choices=[a, b, c]."
    if field == "immutable":
        return "Set immutable to a boolean value: true or false."
    if field == "remember":
        return "Set remember to a boolean value: true or false."
    if field == "compute":
        return "Use a simple compute resolver identifier such as uid or docker_gid."
    if field == "derive":
        if "empty" in message.lower():
            return (
                "Set derive to a non-empty interpolation expression, or remove derive."
            )
        return "Do not combine derive and compute on the same variable."
    if field == "variable":
        return (
            "Ensure recommended and type are compatible and metadata values are valid."
        )
    return "Correct the inline metadata value to satisfy parser requirements."


def _recommended_choice_violations(template_path: Path) -> list[ComplianceViolation]:
    parsed = EnvTemplateParser(template_path).parse()
    violations: list[ComplianceViolation] = []
    for variable in parsed.variables:
        if variable.recommended is None or not variable.choices:
            continue
        allowed = {choice.value for choice in variable.choices}
        if variable.recommended not in allowed:
            line_number = variable.line_number or 1
            violations.append(
                ComplianceViolation(
                    line=line_number,
                    code="INCOMPATIBLE_RECOMMENDED_WITH_CHOICES",
                    message=(
                        f"Variable '{variable.key}' has recommended='{variable.recommended}', "
                        f"but allowed choices are {sorted(allowed)}."
                    ),
                    fix=(
                        "Set recommended to one of the allowed choices, or update choices to "
                        "include the recommended value."
                    ),
                )
            )
    return violations


def _format_violations(
    template_path: Path, violations: list[ComplianceViolation]
) -> str:
    root = _repo_root()
    try:
        display_path = template_path.relative_to(root).as_posix()
    except ValueError:
        display_path = str(template_path)

    lines = [
        f".env.template compliance failed for {display_path}.",
        "Fix the following issue(s):",
    ]
    for issue in violations:
        lines.append(
            f"- line {issue.line} [{issue.code}]: {issue.message} | How to fix: {issue.fix}"
        )
    return "\n".join(lines)


@pytest.mark.parametrize("case", _project_template_cases(), ids=_case_id)
def test_all_projects_define_env_template_file(case: tuple[str, Path]):
    project_name, template_path = case
    assert template_path.exists(), (
        f"Project '{project_name}' is missing its env template file at {template_path}. "
        "How to fix: add .env.template and set the project's env field in 00.api/v1/projects.json."
    )


@pytest.mark.parametrize("case", _project_template_cases(), ids=_case_id)
def test_project_env_template_inline_contract_is_strict(case: tuple[str, Path]):
    _project_name, template_path = case
    assert template_path.exists(), f"Missing template file: {template_path}"

    violations = _validate_inline_contract(template_path)
    assert not violations, _format_violations(template_path, violations)


@pytest.mark.parametrize("case", _project_template_cases(), ids=_case_id)
def test_project_env_template_parser_warnings_fail_hard(case: tuple[str, Path]):
    _project_name, template_path = case
    assert template_path.exists(), f"Missing template file: {template_path}"

    parsed = EnvTemplateParser(template_path).parse()
    if not parsed.warnings:
        return

    violations = [
        ComplianceViolation(
            line=warning.line or 1,
            code=f"PARSER_WARNING:{warning.field}",
            message=warning.message,
            fix=_warn_fix_hint(warning.field, warning.message),
        )
        for warning in parsed.warnings
    ]
    pytest.fail(_format_violations(template_path, violations))


@pytest.mark.parametrize("case", _project_template_cases(), ids=_case_id)
def test_project_env_template_recommended_values_match_choices(case: tuple[str, Path]):
    _project_name, template_path = case
    assert template_path.exists(), f"Missing template file: {template_path}"

    violations = _recommended_choice_violations(template_path)
    assert not violations, _format_violations(template_path, violations)


def _write_template(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sample.env.template"
    path.write_text(body, encoding="utf-8")
    return path


def test_strict_contract_allows_lines_without_required_inline_keys(tmp_path: Path):
    template = _write_template(tmp_path, "APP_NAME= # recommended=demo\n")

    violations = _validate_inline_contract(template)
    assert not any(v.code == "MISSING_REQUIRED_INLINE_KEYS" for v in violations)


def test_strict_contract_fails_on_duplicate_inline_keys(tmp_path: Path):
    template = _write_template(
        tmp_path,
        "PORT= # type=port | prompt=Pick port | prompt=Pick another\n",
    )

    violations = _validate_inline_contract(template)
    assert any(v.code == "DUPLICATE_INLINE_KEY" for v in violations)

    report = _format_violations(template, violations)
    assert "DUPLICATE_INLINE_KEY" in report
    assert "Keep only one" in report


def test_strict_contract_flags_malformed_inline_fragments(tmp_path: Path):
    template = _write_template(
        tmp_path,
        "APP_MODE= # type=string | prompt=Select mode | malformed-fragment\n",
    )

    violations = _validate_inline_contract(template)
    assert any(v.code == "MALFORMED_INLINE_FRAGMENT" for v in violations)

    report = _format_violations(template, violations)
    assert "key=value" in report


def test_strict_contract_allows_optional_inline_keys_to_be_omitted(tmp_path: Path):
    template = _write_template(tmp_path, "APP_MODE= # type=string\n")

    violations = _validate_inline_contract(template)
    assert violations == []


def test_incompatible_recommended_and_choices_get_actionable_message(tmp_path: Path):
    template = _write_template(
        tmp_path,
        "MODE= # recommended=staging | type=string | prompt=Pick mode | choices=[prod, dev]\n",
    )

    violations = _recommended_choice_violations(template)
    assert any(v.code == "INCOMPATIBLE_RECOMMENDED_WITH_CHOICES" for v in violations)

    report = _format_violations(template, violations)
    assert "How to fix" in report
    assert "allowed choices" in report
