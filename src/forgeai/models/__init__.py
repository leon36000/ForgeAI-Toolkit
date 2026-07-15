"""Cœur modèles/gateway (backlog P2, exigences DM-5/DM-6).

- vault : coffre de secrets chiffré (stdlib pur — aucune dépendance externe, invariant
  portabilité `dependencies=[]`).
- routes : registre des routes modèle cloud (provenances connues) — les clés ne sont
  JAMAIS stockées en clair (référencées par empreinte + scellées au coffre).
- probe : test de connexion réel (transport injectable) — une route n'est validée
  qu'après une réponse non vide du fournisseur.
"""
