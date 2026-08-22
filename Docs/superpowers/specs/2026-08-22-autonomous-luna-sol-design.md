# Design — contrat autonome Luna/Sol

## Décision

Luna est l’unique writer actif (`luna_writer`) et Sol est le reviewer actif
(`sol`). La politique autorise exactement deux writer lanes, mais cette limite
ne crée pas de permission d’écriture distante. Le mode de revue actif est
`sol_blind`: contexte frais, aveugle et strictement read-only. Le quorum
historique `multi_vendor` reste disponible uniquement pour les anciennes
preuves.

## Preuve et frontières

Une revue Sol est une revendication vérifiable, pas une autorisation implicite.
Le reçu doit lier le commit de base, le commit et l’arbre examinés, le digest
du diff Git, le prompt et son template, ainsi que les digests séparés des
journaux SDD et du registre de mission. Le dossier de revue, l’identité
canonique `GPT-5.6-Sol`, les marqueurs fresh/blind/read-only et les dates sont
contrôlés avant toute résolution Git. Le digest du diff ne contient jamais les
artefacts de preuve de la revue elle-même.

Le gate possède trois usages distincts :

1. sans drapeau, dépouillement déterministe et contrôle de cohérence interne;
2. en mode PR, liaison de la preuve au diff courant et contrôle de fraîcheur;
3. en mode archive, vérification que chaque preuve encore liante est réellement
   ancêtre de `main`.

Les reçus historiques dont le commit n’est plus ancêtre ne sont pas effacés.
Ils sont retirés de `BINDING.txt`, consignés dans
`evidence/reviews/ARCHIVE-UNMERGED.txt` et nécessitent une nouvelle preuve pour
redevenir liants.

## Terminalité

La story ne peut atteindre `DONE_WITH_EVIDENCE` qu’après les tests, les vues
générées, les registres vérifiés, la revue Sol scellée et le gate archive sur
`main`. Les limites T3 — paiements, secrets de production, suppressions
définitives et engagements externes — restent humaines. Aucun workflow du
contrat ne reçoit `contents: write`, ne force-push ou ne s’auto-écrit.
