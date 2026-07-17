#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.request
from pathlib import Path


class PluginError(Exception):
    pass


REQUIRED_FIELDS = ("id", "name", "source_url", "license", "healthcheck")


def default_existence_check(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status < 400
    except Exception:
        return False


def validate_plugin(plugin: dict, *, existence_check=None) -> list[str]:
    violations = []

    # champs requis absents ou vides + typage strict des champs chaîne
    string_fields = ("id", "name", "source_url", "license")
    for field in REQUIRED_FIELDS:
        val = plugin.get(field)
        if not val:
            violations.append(f"champ requis manquant : '{field}'")
        elif field in string_fields and not isinstance(val, str):
            violations.append(f"champ '{field}' doit être une chaîne")

    # source_url : chaîne https:// pointant vers un dépôt GitHub (critère « existence GitHub »)
    src = plugin.get("source_url")
    if isinstance(src, str) and src:
        if not src.startswith("https://"):
            violations.append("source_url invalide (https requis)")
        elif "github.com" not in src:
            violations.append("source_url doit être un dépôt GitHub (github.com)")

    # healthcheck : chaîne non vide OU objet {"type": ...} — tout autre type est refusé
    hc = plugin.get("healthcheck")
    if hc:  # l'absence/vide est déjà couverte par les champs requis
        if isinstance(hc, dict):
            if not hc.get("type"):
                violations.append("healthcheck sans type")
        elif not isinstance(hc, str):
            violations.append("healthcheck de type invalide (chaîne ou objet {type} attendu)")

    # vérification d’existence GitHub si demandée et source_url valide
    if existence_check is not None and src and isinstance(src, str) and src.startswith("https://"):
        if not existence_check(src):
            violations.append(f"source GitHub introuvable : {src}")

    violations.sort()
    return violations


def load_plugin(path) -> dict:
    p = Path(path)
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise PluginError("Le fichier JSON ne contient pas un objet")
        return data
    except json.JSONDecodeError as e:
        raise PluginError(f"JSON invalide: {e}") from e


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--plugin', required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args(argv)

    plugin = load_plugin(args.plugin)
    check = None if args.offline else default_existence_check
    violations = validate_plugin(plugin, existence_check=check)

    if violations:
        for v in violations:
            print(f"  {v}")
        return 1
    else:
        print(f"PLUGIN-GATE : OK ({plugin.get('id', 'inconnu')} conforme)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
