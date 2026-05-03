"""Tests for secure value generation utilities."""

import re

import bcrypt
import pytest
from utils import GeneratedBcryptHash, SecureValueGenerator


class TestSecureValueGenerator:
    """Test secure generation methods and constraints."""

    def test_generate_password_uses_required_character_classes(self):
        generator = SecureValueGenerator()

        password = generator.generate_password()

        assert len(password) == 20
        assert any(character.islower() for character in password)
        assert any(character.isupper() for character in password)
        assert any(character.isdigit() for character in password)
        assert any(not character.isalnum() for character in password)
        assert all(character not in {"#", "$", "/", "\\"} for character in password)

    def test_generate_password_honors_bounds(self):
        generator = SecureValueGenerator()

        assert len(generator.generate_password(min_length=24)) == 24
        assert len(generator.generate_password(max_length=10)) == 10
        assert len(generator.generate_password(min_length=12, max_length=16)) == 16

    def test_generate_password_rejects_too_small_max_length(self):
        generator = SecureValueGenerator()

        with pytest.raises(ValueError):
            generator.generate_password(max_length=3)

    def test_generate_passphrase_returns_multi_word_value(self):
        generator = SecureValueGenerator()

        passphrase = generator.generate_passphrase()

        assert passphrase.count("-") >= 1
        assert len(passphrase.split("-")) >= 2

    def test_generate_passphrase_honors_bounds(self):
        generator = SecureValueGenerator()

        passphrase = generator.generate_passphrase(min_length=20, max_length=40)

        assert 20 <= len(passphrase) <= 40

    def test_generate_bcrypt_hash_with_provided_password(self):
        generator = SecureValueGenerator()

        result = generator.generate_bcrypthash(password="Sup3r!SecureValue")

        assert isinstance(result, GeneratedBcryptHash)
        assert result.password == "Sup3r!SecureValue"
        assert re.match(r"^\$2[aby]\$", result.bcrypt_hash)
        assert bcrypt.checkpw(
            result.password.encode("utf-8"), result.bcrypt_hash.encode("utf-8")
        )

    def test_generate_bcrypt_hash_generates_password_when_missing(self):
        generator = SecureValueGenerator()

        result = generator.generate_bcrypthash(min_length=18, max_length=22)

        assert isinstance(result, GeneratedBcryptHash)
        assert 18 <= len(result.password) <= 22
        assert any(character.islower() for character in result.password)
        assert any(character.isupper() for character in result.password)
        assert any(character.isdigit() for character in result.password)
        assert any(not character.isalnum() for character in result.password)
        assert bcrypt.checkpw(
            result.password.encode("utf-8"), result.bcrypt_hash.encode("utf-8")
        )

    def test_generate_bcrypt_hash_rejects_invalid_provided_password_bounds(self):
        generator = SecureValueGenerator()

        with pytest.raises(ValueError):
            generator.generate_bcrypthash(password="short", min_length=10)

    def test_generate_string_honors_bounds_and_charset(self):
        generator = SecureValueGenerator()

        generated = generator.generate_string(min_length=12, max_length=12)

        assert len(generated) == 12
        assert all(
            character.isalnum() or character in {"-", "_"} for character in generated
        )

    def test_generate_string_rejects_invalid_bounds(self):
        generator = SecureValueGenerator()

        with pytest.raises(ValueError):
            generator.generate_string(min_length=10, max_length=5)

    def test_generate_base64_honors_bounds_and_charset(self):
        generator = SecureValueGenerator()

        generated = generator.generate_base64(min_length=40, max_length=48)

        assert 40 <= len(generated) <= 48
        assert re.fullmatch(r"[A-Za-z0-9+/=]+", generated)

    def test_generate_base64_urlsafe_honors_bounds_and_charset(self):
        generator = SecureValueGenerator()

        generated = generator.generate_base64_urlsafe(min_length=40, max_length=48)

        assert 40 <= len(generated) <= 48
        assert re.fullmatch(r"[A-Za-z0-9_\-=]+", generated)

    def test_generate_base64_rejects_unsatisfiable_bounds(self):
        generator = SecureValueGenerator()

        with pytest.raises(ValueError):
            generator.generate_base64(min_length=5, max_length=5)
