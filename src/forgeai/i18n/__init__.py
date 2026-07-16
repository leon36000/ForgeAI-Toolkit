"""Système d'internationalisation de ForgeAI Toolkit — stdlib pure."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


_DEFAULT_LOCALES_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "locales"


class MissingTranslation(KeyError):
    """Levée lorsqu'une clé de traduction est absente de la locale courante."""


class Translator:
    """Traducteur chargeant un catalogue JSON plat pour une locale donnée."""

    def __init__(self, locale: str = "fr", locales_dir: Path | None = None) -> None:
        self._locales_dir: Path = locales_dir if locales_dir is not None else _DEFAULT_LOCALES_DIR
        self._locale: str = ""
        self._catalogue: dict[str, str] = {}
        self.set_locale(locale)

    @property
    def locale(self) -> str:
        """Code de la locale courante."""
        return self._locale

    def available(self) -> list[str]:
        """Codes de locale disponibles (fichiers *.json du dossier), triés."""
        return available_locales(self._locales_dir)

    def set_locale(self, code: str) -> None:
        """Change la locale courante en rechargeant le catalogue correspondant."""
        path = self._locales_dir / f"{code}.json"
        if not path.is_file():
            raise ValueError(f"Locale inconnue ou fichier absent : {code!r} ({path})")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Catalogue invalide (attendu dict) pour {code!r}")
        self._catalogue = {str(k): str(v) for k, v in data.items()}
        self._locale = code

    def t(self, key: str, **kwargs: Any) -> str:
        """Retourne la chaîne traduite pour *key*, formatée avec *kwargs* le cas échéant."""
        if key not in self._catalogue:
            raise MissingTranslation(key)
        text = self._catalogue[key]
        if kwargs:
            return text.format(**kwargs)
        return text


_global_translator: Translator | None = None


def available_locales(locales_dir: Path | None = None) -> list[str]:
    """Liste les codes de locale disponibles (stems des *.json), triés.

    N'instancie aucun Translator et ne charge aucun catalogue.
    """
    d = locales_dir if locales_dir is not None else _DEFAULT_LOCALES_DIR
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json") if p.is_file())


def get_translator() -> Translator:
    """Retourne le traducteur module-global (construit paresseusement).

    La locale initiale est lue depuis ``FORGEAI_LANG`` ; si la valeur est
    invalide, retombe silencieusement sur ``"fr"``.
    """
    global _global_translator
    if _global_translator is None:
        code = os.environ.get("FORGEAI_LANG", "fr") or "fr"
        try:
            _global_translator = Translator(code)
        except ValueError:
            _global_translator = Translator("fr")
    return _global_translator


def t(key: str, **kwargs: Any) -> str:
    """Traduction via le traducteur global."""
    return get_translator().t(key, **kwargs)


def set_locale(code: str) -> None:
    """Change la locale du traducteur global."""
    get_translator().set_locale(code)


__all__ = [
    "MissingTranslation",
    "Translator",
    "available_locales",
    "get_translator",
    "set_locale",
    "t",
]
