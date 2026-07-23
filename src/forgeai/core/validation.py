"""Validateurs partagés (source unique — évite la duplication CLI ↔ web ↔ …)."""
import re

# Nom de nœud / hôte : label RFC1123 en minuscules (a-z0-9, tirets/points internes, 1-63 car.).
# Source UNIQUE réutilisée par cli.py et web/server.py (FAI-0016 : dé-duplication).
NODE_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62})$", re.ASCII)
