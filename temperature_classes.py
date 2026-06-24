"""Temperature classes loaded from a runtime YAML config."""

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

import yaml
from babel import Locale

SUPPORTED_COMMENT_LANGS = ("en", "de")


class StateComments(TypedDict):
    """A dictionary of comments for different languages."""

    en: list[str]
    de: list[str]


class TemperatureConfigError(Exception):
    """Raised when the temperature class config is missing or malformed."""


@dataclass
class TemperatureClass:
    """
    A temperature class is a range of temperatures with a minimum temperature,
    an accent color, and a set of comments in different languages.
    """

    min_temperature: float = field()
    color: str = field()
    """Accent color for this temperature class"""
    comments: StateComments = field()

    def pick_comment(self, locale: Locale) -> str:
        """Pick a random comment for this temperature class in the given locale."""
        lang = locale.language

        comment_pool: list[str] = (
            self.comments[lang]  # ty:ignore[invalid-key]
            if lang in self.comments
            else self.comments.get("en", [])
        )

        if comment_pool:
            return random.choice(comment_pool)
        return "Kommentarlos" if lang == "de" else "- No comment -"


@dataclass
class TemperatureClasses:
    """An ordered collection of temperature classes (highest threshold first)."""

    classes: list[TemperatureClass] = field()

    def for_temperature(self, temperature: float) -> TemperatureClass:
        """Return the matching class, falling back to the lowest threshold."""
        for temperature_class in self.classes:
            if temperature_class.min_temperature <= temperature:
                return temperature_class
        # Temperature is below every threshold: use the coldest class.
        return self.classes[-1]


def _parse_class(index: int, raw: object) -> TemperatureClass:
    if not isinstance(raw, dict):
        raise TemperatureConfigError(f"classes[{index}] must be a mapping")

    if "min" not in raw:
        raise TemperatureConfigError(f"classes[{index}] is missing 'min'")
    if not isinstance(raw["min"], (int, float)) or isinstance(raw["min"], bool):  # ty:ignore[invalid-argument-type]
        raise TemperatureConfigError(f"classes[{index}].min must be a number")

    color = raw.get("color")
    if not isinstance(color, str) or not color:
        raise TemperatureConfigError(
            f"classes[{index}].color must be a non-empty string"
        )

    comments_raw = raw.get("comments")
    if not isinstance(comments_raw, dict):
        raise TemperatureConfigError(f"classes[{index}].comments must be a mapping")

    comments: dict[str, list[str]] = {}
    for lang in SUPPORTED_COMMENT_LANGS:
        value = comments_raw.get(lang)
        if not isinstance(value, list) or not value:
            raise TemperatureConfigError(
                f"classes[{index}].comments.{lang} must be a non-empty list"
            )
        if not all(isinstance(item, str) and item for item in value):
            raise TemperatureConfigError(
                f"classes[{index}].comments.{lang} must contain only non-empty strings"
            )
        comments[lang] = value  # ty:ignore[invalid-assignment]

    return TemperatureClass(
        min_temperature=float(raw["min"]),  # ty:ignore[invalid-argument-type]
        color=color,
        comments=StateComments(en=comments["en"], de=comments["de"]),
    )


def load_temperature_classes(path: str | Path) -> TemperatureClasses:
    """Load and validate temperature classes from a YAML file.

    Raises TemperatureConfigError on any problem so the caller can fail fast.
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemperatureConfigError(f"cannot read {config_path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TemperatureConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(data, dict) or "classes" not in data:
        raise TemperatureConfigError("config must have a top-level 'classes' key")

    raw_classes = data["classes"]
    if not isinstance(raw_classes, list) or not raw_classes:
        raise TemperatureConfigError("'classes' must be a non-empty list")

    parsed = [_parse_class(i, raw) for i, raw in enumerate(raw_classes)]
    parsed.sort(key=lambda c: c.min_temperature, reverse=True)
    return TemperatureClasses(classes=parsed)
