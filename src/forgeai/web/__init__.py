"""Interface web locale de ForgeAI Toolkit.

Ré-exporte les points d'entrée du serveur embarqué.
"""
from forgeai.web.server import build_server, serve, web_command

__all__ = ["build_server", "serve", "web_command"]
