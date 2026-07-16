"""Internationalisation (i18n) pour ForgeAI Toolkit — stdlib pure."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_DEFAULT_LOCALES_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "locales"


class MissingTranslation(KeyError):
    """Levée lorsqu'une clé de traduction est absente de la locale courante."""


class Translator:
    """Charge et sert les traductions depuis des catalogues JSON plats."""

    def __init__(self, locale: str = "fr", locales_dir: Path | None = None) -> None:
        self._locales_dir: Path = locales_dir if locales_dir is not None else _DEFAULT_LOCALES_DIR
        self._locale: str = ""
        self._catalogue: dict[str, str] = {}
        self.set_locale(locale)

    # -- API publique -----------------------------------------------------

    def t(self, key: str, **kwargs: Any) -> str:
        """Retourne la chaîne traduite pour *key*, formatée avec *kwargs* le cas échéant."""
        try:
            value = self._catalogue[key]
        except KeyError:
            raise MissingTranslation(key) from None
        if kwargs:
            return value.format(**kwargs)
        return value

    def set_locale(self, code: str) -> None:
        """Change la locale courante en rechargeant le catalogue correspondant."""
        path = self._locales_dir / f"{code}.json"
        if not path.is_file():
            raise ValueError(
                f"Locale '{code}' introuvable (fichier attendu : {path})"
            )
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Le catalogue {path} n'est pas un objet JSON plat.")
        self._catalogue = data
        self._locale = code

    def available(self) -> list[str]:
        """Codes de locale disponibles (fichiers *.json), triés."""
        if not self._locales_dir.is_dir():
            return []
        return sorted(
            p.stem for p in self._locales_dir.glob("*.json") if p.is_file()
        )

    @property
    def locale(self) -> str:
        """Code de la locale courante."""
        return self._locale


# -- Traducteur global paresseux + fonctions de commodité -----------------

_global_translator: Translator | None = None


def get_translator() -> Translator:
    """Retourne le traducteur module-global (créé paresseusement)."""
    global _global_translator
    if _global_translator is None:
        initial_locale = os.environ.get("FORGEAI_LANG", "fr")
        _global_translator = Translator(locale=initial_locale)
    return _global_translator


def t(key: str, **kwargs: Any) -> str:
    """Raccourci : délègue au traducteur global."""
    return get_translator().t(key, **kwargs)


def set_locale(code: str) -> None:
    """Raccourci : change la locale du traducteur global."""
    get_translator().set_locale(code)
