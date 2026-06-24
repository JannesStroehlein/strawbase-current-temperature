"""Temperature classes for different temperature ranges."""

import random
from typing import TypedDict
from dataclasses import field, dataclass
from babel import Locale


class StateComments(TypedDict):
    """A dictionary of comments for different languages."""

    en: list[str]
    de: list[str]


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

    @staticmethod
    def for_temperature(temperature: float) -> TemperatureClass:
        """Return the temperature class for the given temperature."""
        return next(x for x in STATE_CLASSES if x.min_temperature <= temperature)

    def pick_comment(self, locale: Locale) -> str:
        """Pick a random comment for this temperature class in the given locale."""
        lang = locale.language

        comment_pool: list[str] = (
            self.comments[lang]  # ty:ignore[invalid-key]
            if lang in self.comments
            else self.comments.get("en", [])
        )

        comment = random.sample(comment_pool, 1)
        if comment and len(comment) == 1:
            return comment[0]
        return "Kommentarlos" if lang == "de_DE" else "- No comment -"


STATE_CLASSES: list[TemperatureClass] = sorted(
    [
        TemperatureClass(
            0,
            "#60a5fa",
            {
                "en": ["Freezing"],
                "de": ["Bibberkalt", "Brrrrt 🥶"],
            },
        ),
        TemperatureClass(16, "#34d399", {"en": ["Perfect"], "de": ["Perfekt"]}),
        TemperatureClass(22, "#fbbf24", {"en": ["Too hot"], "de": ["Es ist zu warm."]}),
        TemperatureClass(
            26,
            "#f87171",
            {
                "en": ["Hot"],
                "de": [
                    "Höllenfeuer",
                    "Warum ich?",
                    "Wenn Dachgeschoss Wohnungen Öfen sind: Macht ein Ventilator dann Umluft?",
                    "Perfektes Wetter um auf dem Weg zum Eiscafé zu verbrennen",
                    "Hier hilft nur noch der Arzt",
                    "Kauft mir jemand eine Klimaanlage?",
                    "Holt mich hier raus!",
                ],
            },
        ),
    ],
    key=lambda x: x.min_temperature,
    reverse=True,
)
