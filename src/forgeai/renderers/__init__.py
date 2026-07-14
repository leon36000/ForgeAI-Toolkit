"""Rendu double backend : Compose (P1-S06) et K3s (P1-S07)."""

from forgeai.renderers.compose import render_compose
from forgeai.renderers.k3s import render_k3s

__all__ = ["render_compose", "render_k3s"]
