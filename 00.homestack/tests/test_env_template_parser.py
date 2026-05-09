"""Tests for `.env.template` parser behavior."""

from pathlib import Path

import pytest
from parsers import EnvTemplateParser


def _write_template(tmp_path: Path, content: str) -> Path:
    file_path = tmp_path / "sample.env.template"
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestEnvTemplateParser:
    """Test cases for EnvTemplateParser."""

    def test_parse_metadata_and_variables(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """# METADATA --- START
            Description=Demo description
            Required=true
            # METADATA --- END

            APP_NAME= # recommended=pihole | type=string(3,20) | prompt=Enter app name | instruction=Use lowercase | choices=[pihole, adguard] | immutable=false | description=Application name
            PORT= # recommended=80 | type=port | choices=[80 (description=HTTP, default=true), 443 (description=HTTPS)]
            """,
        )

        parser = EnvTemplateParser(template_path)
        parsed = parser.parse()

        assert parsed.metadata.description == "Demo description"
        assert parsed.metadata.required is True
        assert len(parsed.variables) == 2
        assert parsed.variables[0].key == "APP_NAME"
        assert parsed.variables[0].value_type is not None
        assert parsed.variables[0].value_type.raw == "string(3,20)"
        assert parsed.variables[1].choices is not None
        assert parsed.variables[1].choices[0].default is True
        assert parsed.variables[1].immutable is False
        assert parsed.warnings == []

    def test_parse_empty_choices(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # recommended=value | type=string | choices=[]
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert len(parsed.variables) == 1
        assert parsed.variables[0].choices == []

    def test_compute_metadata_is_preserved_in_extra_metadata(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """UID= # type=int | compute=uid
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert len(parsed.variables) == 1
        assert parsed.variables[0].extra_metadata["compute"] == "uid"

    def test_malformed_compute_adds_warning(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """UID= # type=int | compute=id -u
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert len(parsed.variables) == 1
        assert any(w.field == "compute" for w in parsed.warnings)

    def test_duplicate_inline_key_warns_last_wins(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """PORT= # recommended=80 | recommended=81 | type=port
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert parsed.variables[0].recommended == "81"
        assert any(
            "Duplicate inline metadata key" in warning.message
            for warning in parsed.warnings
        )

    def test_malformed_type_adds_warning_and_continues(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """PORT= # recommended=80 | type=port(1,2)
NAME= # recommended=demo | type=string
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert len(parsed.variables) == 2
        assert parsed.variables[0].value_type is None
        assert parsed.variables[1].value_type is not None
        assert any(w.field == "type" for w in parsed.warnings)

    def test_invalid_choices_syntax_warns(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """MODE= # type=string | choices=always,never
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert len(parsed.variables) == 1
        assert parsed.variables[0].choices == []
        assert any(
            "Choices must be enclosed" in warning.message for warning in parsed.warnings
        )

    def test_invalid_immutable_bool_warns(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # immutable=maybe | type=string
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert parsed.variables[0].immutable is False
        assert any(w.field == "immutable" for w in parsed.warnings)

    def test_missing_immutable_defaults_false(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # recommended=demo | type=string | prompt=Enter value | choices=[]
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert len(parsed.variables) == 1
        assert parsed.variables[0].immutable is False

    def test_missing_remember_defaults_false(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # recommended=demo | type=password(8,32)
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert len(parsed.variables) == 1
        assert parsed.variables[0].remember is False

    def test_parse_remember_true(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # recommended=abcdefgh | type=password(8,32) | remember=true
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert len(parsed.variables) == 1
        assert parsed.variables[0].remember is True
        assert parsed.warnings == []

    def test_invalid_remember_bool_warns(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # type=password(8,32) | remember=maybe
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert parsed.variables[0].remember is False
        assert any(w.field == "remember" for w in parsed.warnings)

    def test_recommended_none_is_treated_as_unset(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """NEXTAUTH_SECRET= # recommended=None | type=passphrase(32)
""",
        )
        parsed = EnvTemplateParser(template_path).parse()

        assert len(parsed.variables) == 1
        assert parsed.variables[0].recommended is None
        assert not any(
            "Variable validation failed" in warning.message
            for warning in parsed.warnings
        )

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            EnvTemplateParser("/nonexistent/path/file.env.template")

    def test_utf8_content_is_preserved(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """KEY= # type=string | prompt=Entrë value | description=Café setting
""",
        )
        parsed = EnvTemplateParser(template_path).parse()
        assert parsed.variables[0].prompt == "Entrë value"
        assert "Café" in (parsed.variables[0].description or "")

    def test_parse_full_template_covers_all_supported_types(self, tmp_path: Path):
        template_path = _write_template(
            tmp_path,
            """# METADATA --- START
            # DO NOT CHANGE THE BELOW
            Description=Environment variables for coverage test.
            Required=true
            # METADATA --- END

            DOCKER_IMAGE_PH_PIHOLE= # recommended=mpgirro/pihole-unbound:latest | type=string | prompt=select the pihole docker image | instruction=Pick this one | choices=[mpgirro/pihole-unbound:latest] | immutable=true | description=Docker image
            HOST_NAME_BOUNDED= # recommended=host01 | type=string(3,16) | choices=[] | immutable=false | description=Bounded string
            PIHOLE_PASSWORD= # recommended=super-secret-password | type=password | prompt=Enter password | instruction=Choose carefully | choices=[] | immutable=false | description=Pihole password
            PASSWORD_BOUNDED= # recommended=abc123 | type=password(6,20) | choices=[] | immutable=false | description=Bounded password
            VPN_PASSPHRASE= # recommended=alpha bravo | type=passphrase | prompt=Enter passphrase | instruction=Use words | choices=[] | immutable=false | description=Passphrase
            VPN_PASSPHRASE_BOUNDED= # recommended=alpha bravo charlie | type=passphrase(5,64) | choices=[] | immutable=false | description=Bounded passphrase
            API_TOKEN= # recommended=QWxwaGFTZWNyZXQ= | type=base64(8,128) | choices=[] | immutable=false | description=Base64 token
            API_TOKEN_URLSAFE= # recommended=QWxwaGFTZWNyZXQ= | type=base64urlsafe(8,128) | choices=[] | immutable=false | description=URL-safe base64 token
            BCRYPT_HASH= # recommended=$2b$12$abcdefghijklmnopqrstuv1234567890abcdefghijklmnopqrstuv | type=bcrypthash | choices=[] | immutable=true | description=Bcrypt hash
            CPU_MIN_PH_PIHOLE= # recommended=0.05 | type=float | prompt=Enter min cpu | instruction=Fractional CPU | choices=[] | immutable=false | description=Min CPU
            CPU_MAX_BOUNDED= # recommended=1.50 | type=float(0.10,2.00) | choices=[] | immutable=false | description=Bounded float
            PORT_PH_PIHOLE= # recommended=80 | type=int | prompt=Enter web port | instruction=Use default | choices=[80] | immutable=true | description=Web interface port
            PORT_RANGE_SAMPLE= # recommended=53 | type=int(1,65535) | choices=[] | immutable=false | description=Bounded int
            RAM_MIN_PH_PIHOLE= # recommended=6M | type=memory | prompt=Enter min ram | instruction=Use K/M/G/T suffix | choices=[] | immutable=false | description=Min RAM
            IP_PH_PIHOLE= # recommended=172.16.0.2 | type=ip | prompt=Enter static ip | instruction=Leave default if unsure | choices=[] | immutable=false | description=Static IP
            SERVICE_PORT= # recommended=8080 | type=port | prompt=Enter service port | instruction=Standard app port | choices=[] | description=Port type
            FEATURE_ENABLED= # recommended=TrUe | type=boolean | prompt=Enable feature? | instruction=true or false | choices=[] | description=Feature flag
            """,
        )

        parsed = EnvTemplateParser(template_path).parse()

        assert parsed.metadata.required is True
        assert len(parsed.variables) == 17
        assert parsed.warnings == []

        by_key = {variable.key: variable for variable in parsed.variables}

        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].value_type is not None
        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].value_type.raw == "string"
        assert (
            by_key["DOCKER_IMAGE_PH_PIHOLE"].prompt == "select the pihole docker image"
        )
        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].instruction == "Pick this one"
        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].choices is not None
        assert len(by_key["DOCKER_IMAGE_PH_PIHOLE"].choices or []) == 1
        assert (by_key["DOCKER_IMAGE_PH_PIHOLE"].choices or [])[
            0
        ].value == "mpgirro/pihole-unbound:latest"
        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].immutable is True
        assert by_key["DOCKER_IMAGE_PH_PIHOLE"].description == "Docker image"

        assert by_key["HOST_NAME_BOUNDED"].value_type is not None
        assert by_key["HOST_NAME_BOUNDED"].value_type.raw == "string(3,16)"
        assert by_key["HOST_NAME_BOUNDED"].choices == []
        assert by_key["HOST_NAME_BOUNDED"].immutable is False
        assert by_key["HOST_NAME_BOUNDED"].description == "Bounded string"

        assert by_key["PIHOLE_PASSWORD"].value_type is not None
        assert by_key["PIHOLE_PASSWORD"].value_type.raw == "password"
        assert by_key["PIHOLE_PASSWORD"].prompt == "Enter password"
        assert by_key["PIHOLE_PASSWORD"].instruction == "Choose carefully"
        assert by_key["PIHOLE_PASSWORD"].choices == []
        assert by_key["PIHOLE_PASSWORD"].immutable is False
        assert by_key["PIHOLE_PASSWORD"].description == "Pihole password"

        assert by_key["PASSWORD_BOUNDED"].value_type is not None
        assert by_key["PASSWORD_BOUNDED"].value_type.raw == "password(6,20)"

        assert by_key["VPN_PASSPHRASE"].value_type is not None
        assert by_key["VPN_PASSPHRASE"].value_type.raw == "passphrase"

        assert by_key["VPN_PASSPHRASE_BOUNDED"].value_type is not None
        assert by_key["VPN_PASSPHRASE_BOUNDED"].value_type.raw == "passphrase(5,64)"

        assert by_key["API_TOKEN"].value_type is not None
        assert by_key["API_TOKEN"].value_type.raw == "base64(8,128)"

        assert by_key["API_TOKEN_URLSAFE"].value_type is not None
        assert by_key["API_TOKEN_URLSAFE"].value_type.raw == "base64urlsafe(8,128)"

        assert by_key["BCRYPT_HASH"].value_type is not None
        assert by_key["BCRYPT_HASH"].value_type.raw == "bcrypthash"

        assert by_key["CPU_MIN_PH_PIHOLE"].value_type is not None
        assert by_key["CPU_MIN_PH_PIHOLE"].value_type.raw == "float"

        assert by_key["CPU_MAX_BOUNDED"].value_type is not None
        assert by_key["CPU_MAX_BOUNDED"].value_type.raw == "float(0.10,2.00)"

        assert by_key["PORT_PH_PIHOLE"].value_type is not None
        assert by_key["PORT_PH_PIHOLE"].value_type.raw == "int"
        assert by_key["PORT_PH_PIHOLE"].prompt == "Enter web port"
        assert by_key["PORT_PH_PIHOLE"].instruction == "Use default"
        assert by_key["PORT_PH_PIHOLE"].choices is not None
        assert (by_key["PORT_PH_PIHOLE"].choices or [])[0].value == "80"
        assert by_key["PORT_PH_PIHOLE"].immutable is True
        assert by_key["PORT_PH_PIHOLE"].description == "Web interface port"

        assert by_key["PORT_RANGE_SAMPLE"].value_type is not None
        assert by_key["PORT_RANGE_SAMPLE"].value_type.raw == "int(1,65535)"

        assert by_key["RAM_MIN_PH_PIHOLE"].value_type is not None
        assert by_key["RAM_MIN_PH_PIHOLE"].value_type.raw == "memory"
        assert by_key["RAM_MIN_PH_PIHOLE"].prompt == "Enter min ram"
        assert by_key["RAM_MIN_PH_PIHOLE"].instruction == "Use K/M/G/T suffix"
        assert by_key["RAM_MIN_PH_PIHOLE"].choices == []
        assert by_key["RAM_MIN_PH_PIHOLE"].immutable is False
        assert by_key["RAM_MIN_PH_PIHOLE"].description == "Min RAM"

        assert by_key["IP_PH_PIHOLE"].value_type is not None
        assert by_key["IP_PH_PIHOLE"].value_type.raw == "ip"
        assert by_key["IP_PH_PIHOLE"].prompt == "Enter static ip"
        assert by_key["IP_PH_PIHOLE"].instruction == "Leave default if unsure"
        assert by_key["IP_PH_PIHOLE"].choices == []
        assert by_key["IP_PH_PIHOLE"].immutable is False
        assert by_key["IP_PH_PIHOLE"].description == "Static IP"

        assert by_key["SERVICE_PORT"].value_type is not None
        assert by_key["SERVICE_PORT"].value_type.raw == "port"
        assert by_key["SERVICE_PORT"].prompt == "Enter service port"
        assert by_key["SERVICE_PORT"].instruction == "Standard app port"
        assert by_key["SERVICE_PORT"].choices == []
        assert by_key["SERVICE_PORT"].immutable is False
        assert by_key["SERVICE_PORT"].description == "Port type"

        assert by_key["FEATURE_ENABLED"].value_type is not None
        assert by_key["FEATURE_ENABLED"].value_type.raw == "boolean"
        assert by_key["FEATURE_ENABLED"].recommended == "true"
        assert by_key["FEATURE_ENABLED"].prompt == "Enable feature?"
        assert by_key["FEATURE_ENABLED"].instruction == "true or false"
        assert by_key["FEATURE_ENABLED"].choices == []
        assert by_key["FEATURE_ENABLED"].immutable is False
        assert by_key["FEATURE_ENABLED"].description == "Feature flag"
