"""Secure value generation helpers for env template driven workflows."""

from __future__ import annotations

import base64
import string
from dataclasses import dataclass
from secrets import choice as secret_choice
from secrets import randbelow, token_bytes

import bcrypt
from xkcdpass.xkcd_password import generate_wordlist

LOWERCASE_CHARS = string.ascii_lowercase
UPPERCASE_CHARS = string.ascii_uppercase
DIGIT_CHARS = string.digits
SPECIAL_CHARS = "!%&()*+,-.:;<=>?@[]^_{|}~"
SAFE_STRING_CHARS = string.ascii_letters + string.digits + "-_"


@dataclass(frozen=True)
class GeneratedBcryptHash:
    """Result object for bcrypt generation.

    Attributes:
        password: Plaintext password used to produce the bcrypt hash.
        bcrypt_hash: UTF-8 decoded bcrypt hash string.
    """

    password: str
    bcrypt_hash: str


class SecureValueGenerator:
    """Generate strong passwords, passphrases, bcrypt hashes, and strings.

    Passwords always include lowercase, uppercase, digits, and special characters,
    and exclude '#', '$', '/', and '\\'. Passphrases use a wordlist-based strategy
    with cryptographically secure word selection.
    """

    def __init__(
        self,
        *,
        default_password_length: int = 20,
        default_passphrase_words: int = 5,
        default_string_length: int = 16,
        separator: str = "-",
        bcrypt_rounds: int = 12,
    ) -> None:
        self.default_password_length = default_password_length
        self.default_passphrase_words = default_passphrase_words
        self.default_string_length = default_string_length
        self.separator = separator
        self.bcrypt_rounds = bcrypt_rounds
        self._wordlist = list(generate_wordlist())

        if not self._wordlist:
            raise ValueError("xkcdpass wordlist is empty")

    def generate_password(
        self, min_length: int | None = None, max_length: int | None = None
    ) -> str:
        """Generate a strong password that satisfies character class requirements."""
        target_length = self._resolve_length(
            min_length=min_length,
            max_length=max_length,
            default_length=self.default_password_length,
            minimum_allowed=4,
            field_name="password",
        )

        required_sets = [LOWERCASE_CHARS, UPPERCASE_CHARS, DIGIT_CHARS, SPECIAL_CHARS]
        password_chars = [secret_choice(characters) for characters in required_sets]
        combined_chars = "".join(required_sets)

        while len(password_chars) < target_length:
            password_chars.append(secret_choice(combined_chars))

        self._secure_shuffle(password_chars)
        return "".join(password_chars)

    def generate_passphrase(
        self, min_length: int | None = None, max_length: int | None = None
    ) -> str:
        """Generate a strong word-based passphrase within optional length bounds."""
        min_bound, max_bound = self._normalize_bounds(
            min_length=min_length,
            max_length=max_length,
            minimum_allowed=3,
            field_name="passphrase",
        )

        feasible_word_counts = [
            count
            for count in range(2, 13)
            if self._word_count_can_fit(count, min_bound, max_bound)
        ]
        if not feasible_word_counts:
            raise ValueError(
                "No passphrase configuration can satisfy the requested bounds"
            )

        ordered_counts = sorted(
            feasible_word_counts,
            key=lambda count: (abs(count - self.default_passphrase_words), count),
        )

        for word_count in ordered_counts:
            for _ in range(256):
                words = [secret_choice(self._wordlist) for _ in range(word_count)]
                passphrase = self.separator.join(words)
                if self._within_bounds(len(passphrase), min_bound, max_bound):
                    return passphrase

        raise ValueError("Unable to generate a passphrase within the requested bounds")

    def generate_bcrypthash(
        self,
        password: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> GeneratedBcryptHash:
        """Hash a provided password or a newly generated strong password with bcrypt."""
        plaintext = password
        if plaintext is None:
            plaintext = self.generate_password(
                min_length=min_length, max_length=max_length
            )
        else:
            self._validate_text_input(plaintext, field_name="password")
            if min_length is not None and len(plaintext) < min_length:
                raise ValueError("Provided password is shorter than min_length")
            if max_length is not None and len(plaintext) > max_length:
                raise ValueError("Provided password is longer than max_length")

        hashed = bcrypt.hashpw(
            plaintext.encode("utf-8"),
            bcrypt.gensalt(rounds=self.bcrypt_rounds),
        )
        return GeneratedBcryptHash(
            password=plaintext, bcrypt_hash=hashed.decode("utf-8")
        )

    def generate_string(
        self, min_length: int | None = None, max_length: int | None = None
    ) -> str:
        """Generate a safe random string within optional bounds."""
        target_length = self._resolve_length(
            min_length=min_length,
            max_length=max_length,
            default_length=self.default_string_length,
            minimum_allowed=1,
            field_name="string",
        )
        return "".join(secret_choice(SAFE_STRING_CHARS) for _ in range(target_length))

    def generate_base64(
        self, min_length: int | None = None, max_length: int | None = None
    ) -> str:
        """Generate a base64-encoded token within optional length bounds."""
        return self._generate_base64_encoded(
            min_length=min_length,
            max_length=max_length,
            urlsafe=False,
            field_name="base64",
        )

    def generate_base64_urlsafe(
        self, min_length: int | None = None, max_length: int | None = None
    ) -> str:
        """Generate a URL-safe base64-encoded token within optional length bounds."""
        return self._generate_base64_encoded(
            min_length=min_length,
            max_length=max_length,
            urlsafe=True,
            field_name="base64urlsafe",
        )

    def _resolve_length(
        self,
        *,
        min_length: int | None,
        max_length: int | None,
        default_length: int,
        minimum_allowed: int,
        field_name: str,
    ) -> int:
        min_bound, max_bound = self._normalize_bounds(
            min_length=min_length,
            max_length=max_length,
            minimum_allowed=minimum_allowed,
            field_name=field_name,
        )

        if min_bound is None and max_bound is None:
            return default_length

        lower = min_bound if min_bound is not None else minimum_allowed
        upper = max_bound if max_bound is not None else max(default_length, lower)

        candidate = default_length
        if candidate < lower:
            candidate = lower
        if candidate > upper:
            candidate = upper

        return candidate

    def _generate_base64_encoded(
        self,
        *,
        min_length: int | None,
        max_length: int | None,
        urlsafe: bool,
        field_name: str,
    ) -> str:
        min_bound, max_bound = self._normalize_bounds(
            min_length=min_length,
            max_length=max_length,
            minimum_allowed=4,
            field_name=field_name,
        )

        # 32 random bytes is the default source entropy for base64 secrets.
        preferred_bytes = 32
        min_bytes = 1
        max_bytes = 4096

        candidates = list(range(preferred_bytes, max_bytes + 1)) + list(
            range(preferred_bytes - 1, min_bytes - 1, -1)
        )
        for byte_count in candidates:
            encoded = self._encode_random_bytes(byte_count, urlsafe=urlsafe)
            if self._within_bounds(len(encoded), min_bound, max_bound):
                return encoded

        raise ValueError(
            f"Unable to generate {field_name} value within the requested bounds"
        )

    @staticmethod
    def _encode_random_bytes(byte_count: int, *, urlsafe: bool) -> str:
        raw = token_bytes(byte_count)
        if urlsafe:
            return base64.urlsafe_b64encode(raw).decode("utf-8")
        return base64.b64encode(raw).decode("utf-8")

    def _normalize_bounds(
        self,
        *,
        min_length: int | None,
        max_length: int | None,
        minimum_allowed: int,
        field_name: str,
    ) -> tuple[int | None, int | None]:
        if min_length is not None and min_length < minimum_allowed:
            raise ValueError(
                f"{field_name} min_length must be at least {minimum_allowed}"
            )
        if max_length is not None and max_length < minimum_allowed:
            raise ValueError(
                f"{field_name} max_length must be at least {minimum_allowed}"
            )
        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise ValueError(
                f"{field_name} min_length cannot be greater than max_length"
            )
        return min_length, max_length

    def _word_count_can_fit(
        self,
        word_count: int,
        min_length: int | None,
        max_length: int | None,
    ) -> bool:
        separator_length = len(self.separator)
        shortest_word = min(len(word) for word in self._wordlist)
        longest_word = max(len(word) for word in self._wordlist)

        shortest_possible = (
            word_count * shortest_word + (word_count - 1) * separator_length
        )
        longest_possible = (
            word_count * longest_word + (word_count - 1) * separator_length
        )

        if min_length is not None and longest_possible < min_length:
            return False
        if max_length is not None and shortest_possible > max_length:
            return False
        return True

    @staticmethod
    def _within_bounds(
        length: int, min_length: int | None, max_length: int | None
    ) -> bool:
        if min_length is not None and length < min_length:
            return False
        if max_length is not None and length > max_length:
            return False
        return True

    @staticmethod
    def _secure_shuffle(items: list[str]) -> None:
        for index in range(len(items) - 1, 0, -1):
            swap_index = randbelow(index + 1)
            items[index], items[swap_index] = items[swap_index], items[index]

    @staticmethod
    def _validate_text_input(value: str, *, field_name: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must be a non-empty string")
