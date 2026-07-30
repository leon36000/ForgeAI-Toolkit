# Décision d'architecture — issue #286 : verrou de fichier portable

| Champ | Valeur |
|---|---|
| Statut | PROPOSÉ — prêt pour implémentation sous TDD |
| Portée | `src/forgeai/core/registre.py`, `src/forgeai/models/_locking.py`, nouveau module `src/forgeai/core/_portable_lock.py` |
| Option retenue | **A — verrou portable unique** (`fcntl.flock` POSIX / `msvcrt.locking` Windows) derrière une API commune |
| Hors périmètre | `ide/guard_fs.py` (contrat assumé, inchangé) |

---

## 1. Option retenue : A, avec sélection de backend au chargement du module

Le backend est choisi une fois, à l'import (`os.name == "nt"` → `msvcrt` ; `os.name == "posix"` → `fcntl` ; **tout autre → `RuntimeError` immédiat à l'import**). Aucune branche par appel, aucun chemin no-op n'existe dans le code.

Confrontation aux contraintes, une ligne chacune :

- **C1 (jamais de dégradation silencieuse)** : les deux backends sont de vrais verrous noyau ; sur plateforme inconnue l'échec est franc et à l'import — il est structurellement impossible d'écrire hors verrou.
- **C2 (libération à la mort)** : `flock` et `msvcrt.locking` (= `LockFile` Win32) sont relâchés par le noyau à la fermeture du descripteur, kill -9 / TerminateProcess inclus — c'est précisément ce qui **disqualifie B** (sentinelle `O_EXCL` : orphelin garanti sur crash ; la récupération d'orphelin exigerait heartbeat + détection de pid, hors stdlib crédible et improuvable en CI).
- **C3 (durcissements)** : la sémantique d'ouverture/validation de `file_lock` (O_NOFOLLOW, refus non-régulier, 0o600) est orthogonale au backend de verrouillage ; seuls les deux appels `flock` internes sont remplacés.
- **C4 (stdlib)** : `fcntl` et `msvcrt` sont stdlib, chacun sur sa plateforme ; zéro dépendance.
- **C5 (tests RED-capables)** : le test de concurrence passe à un contexte multiprocessing choisi par plateforme (`fork` POSIX / `spawn` Windows), worker top-level picklable, assertions inchangées (160 entrées, `seq` = 1..160 sans doublon, chaîne intègre) — la course spawn est tout aussi fatale sans verrou que la course fork, le test reste donc RED-capable sur Windows.
- **C6 (CLI)** : `registre.py` importe le module en absolu avec repli déterministe par chargement du fichier frère via `importlib.util` (chemin dérivé de `__file__`), donc `python registre.py append …` survit sans toucher à `sys.path`.

**Rejets** : B viole C2 sans remède stdlib ; C viole la vocation universelle du produit et la demande explicite du propriétaire de compléter cette issue.

## 2. Emplacement et interface

**Module** : `src/forgeai/core/_portable_lock.py` — stdlib seul, aucun import intra-produit (donc aucun cycle possible depuis `models`). Privé (underscore) : la surface publique reste `registre.append` et `file_lock`.

**API (basée sur le descripteur, bloquante bornée)** :

```python
class LockTimeoutError(TimeoutError): ...

def acquire_exclusive(fd: int, *, timeout_s: float = 30.0, retry_s: float = 0.05) -> None
def release_exclusive(fd: int) -> None

@contextlib.contextmanager
def locked_exclusive(fd: int, *, timeout_s: float = 30.0, retry_s: float = 0.05) -> Iterator[None]
```

**Sémantique exacte** :

- **Boucle de réessai** : tentative *non bloquante* à chaque itération (`flock(LOCK_EX | LOCK_NB)` / `msvcrt.locking(fd, LK_NBLCK, 1)`), sommeil `retry_s` (défaut 50 ms) entre tentatives, horloge `time.monotonic`. On n'utilise **pas** `LK_LOCK` : son comportement interne (1 essai/seconde × 10 puis `OSError`) est opaque, non paramétrable, et transformerait une contention légitime en crash à 10 s — le piège Windows documenté. Notre boucle rend la politique identique et testable sur les deux OS.
- **Expiration** : à l'échéance `timeout_s` (défaut 30 s), lève `LockTimeoutError`. L'appelant laisse propager : échec franc, jamais d'écriture hors section critique (C1).
- **Plage verrouillée** : **1 octet à l'offset 0**, point fixe. `acquire_exclusive` et `release_exclusive` effectuent chacun `os.lseek(fd, 0, SEEK_SET)` immédiatement avant l'appel système : la position courante de l'appelant est sans effet, et le déverrouillage (`LK_UNLCK` / `LOCK_UN`) frappe exactement la même plage — exigence Windows respectée par construction. Verrou de section critique global par fichier, pas de verrouillage granulaire (la section critique registre = lire-tout + écrire-un).
- **Fichier vide** : verrouiller [0,1) au-delà d'EOF est licite des deux côtés — `LockFile` accepte explicitement une plage au-delà de la fin de fichier, `flock` porte sur le fichier et non sur des octets. Le cas « registre vide, première entrée » est couvert par construction **et** par un test dédié (§4).

**Cible du verrou dans `registre.append` : inchangée — le descripteur du fichier de données lui-même** (ouvert `a+`). Pas de bascule sur un `.lock` séparé, pour trois raisons : (i) conserver la cible minimise le delta de comportement et garde le test RED existant pertinent ; (ii) un `.lock` séparé ajoute un second objet filesystem dont les races de création/suppression sont aggravées sous Windows (un fichier ouvert n'y peut être ni supprimé ni renommé — piège documenté) pour un gain nul ; (iii) lecture intégrale et append se font sous le même descripteur, sans fenêtre entre verrou et lecture. Interaction notée : ouvert en `a`, toute écriture va en fin de fichier quel que soit `lseek` — le `lseek(0)` du verrou ne corrompt pas la sémantique d'append, et la lecture refait `seek(0)` explicitement comme aujourd'hui.

`_locking.py`, lui, **conserve** son `.lock` séparé : c'est un verrou de transaction multi-fichiers (vault + routes + WAL), il ne protège pas un fichier unique — les deux stratégies coexistent, chacune à sa place.

## 3. Plan de migration

**`core/registre.py`**
- Suppression de `import fcntl` (l.18). Import `from forgeai.core._portable_lock import locked_exclusive, LockTimeoutError`, encapsulé dans un `try/except ImportError` dont le repli charge `Path(__file__).with_name("_portable_lock.py")` via `importlib.util.spec_from_file_location` — préserve C6 sans toucher `sys.path`.
- Dans `append()` : la paire `flock(LOCK_EX)` … `flush`+`fsync` … `flock(LOCK_UN)` devient `with locked_exclusive(f.fileno(), timeout_s=APPEND_LOCK_TIMEOUT_S):` entourant **exactement** la section critique actuelle (lecture intégrale → calcul `seq`/`prev_hash` → écriture d'une ligne → `flush` + `fsync`). Constante de module `APPEND_LOCK_TIMEOUT_S = 30.0`.
- **Ne change pas** : format JSONL, chaînage `prev_hash`, HMAC, `seq = len(entries)+1`, CLI `append`/`verify`, signatures publiques, gestion d'erreurs métier.

**`models/_locking.py`**
- Signature `file_lock(path)` et **tous** les durcissements conservés : `O_NOFOLLOW` (via `getattr(os, "O_NOFOLLOW", 0)`), refus si non-régulier (`S_ISREG` sur `fstat`), mode `0o600`, `O_CLOEXEC` POSIX / `O_NOINHERIT` Windows (résolution par `getattr`, pattern déjà en place).
- Seuls les appels `fcntl.flock` internes deviennent `acquire_exclusive(fd, …)` / `release_exclusive(fd)` dans le `try/finally` existant. Import absolu depuis `forgeai.core` (models dépend déjà de core).
- Timeout des transactions : même défaut 30 s — les transactions sont courtes, et l'échec franc à l'échéance emprunte le chemin de recovery WAL déjà existant.

**`ide/guard_fs.py` (template généré) : inchangé**, reste sur son contrat assumé. Justification : c'est un script autonome *par construction* — il s'exécute dans un workspace étranger où forgeai n'est pas installé, donc ne peut pas importer `forgeai.core` ; un seul agent par workspace ; et son invariant de sécurité (le refus tient) ne dépend pas de la journalisation. Y dupliquer la machine à verrous grossirait l'artefact généré et sa surface de maintenance pour un gain nul. On ajoute une ligne au commentaire d'en-tête pointant vers `_portable_lock` pour les futurs lecteurs.

## 4. Stratégie de test multi-OS

- **Concurrence registre (existant, adapté)** : `ctx = mp.get_context("fork" if os.name == "posix" else "spawn")` ; worker = fonction top-level du module de test (exigence spawn : picklable, import sans effet de bord). P=8 × K=20 → 160 entrées, `seq` uniques, `verify` intègre. RED-capable des deux côtés : sans verrou, la race fork (POSIX) et la race spawn (Windows) produisent seq dupliqués / `prev_hash` divergents — preuve de course déjà démontrée côté fork, mécaniquement identique côté spawn.
- **Preuve que le verrou Windows verrouille vraiment (nouveau, RED-capable par construction)** — `test_exclusion_reelle` : le parent acquiert le verrou sur un fichier temporaire ; un enfant (contexte `spawn`, ou `subprocess` sur un helper module-level) tente `acquire_exclusive(fd, timeout_s=0.5)` sur le même fichier → **doit** lever `LockTimeoutError` avec durée mesurée ≥ 0,5 s ; le parent relâche ; l'enfant réessaie → acquisition immédiate. Un backend Windows no-op ferait réussir instantanément la première acquisition enfant → test ROUGE. C'est la réponse directe à C1/C5 : il prouve l'exclusion mutuelle, pas l'absence de crash. Il tourne à l'identique sur POSIX.
- **Fichier vide (nouveau)** : acquire/release sur fichier de 0 octet, puis premier append concurrentiel — valide la plage [0,1) au-delà d'EOF sur Windows.
- **Timeout (nouveau)** : verrou tenu, second acquéreur `timeout_s=0.2` → `LockTimeoutError`, durée mesurée dans [0,2 s ; 2 s[.
- **CLI (C6)** : 4 sous-processus × 5 appends via `[sys.executable, "-m", "forgeai.core.registre", "append", f]`, plus un test d'invocation directe par chemin de fichier pour le repli importlib → 20 entrées intègres, sur les deux OS.
- **Matrice CI** : **étendre le job existant `guard-fs-multi-os`, ne pas le dupliquer** — son mandat (prouver les comportements filesystem sensibles à l'OS sur ubuntu/macos/windows) couvre exactement ce périmètre ; on y ajoute `tests/core/test_portable_lock.py` et le test de concurrence registre adapté. Un second job Windows dupliquerait setup et minutes CI sans information supplémentaire ; le nom du job est inchangé pour ne pas casser les required checks.

## 5. Risques résiduels assumés

1. **Nature consultative des deux backends** : un processus étranger écrivant sans passer par le verrou n'est pas exclu — identique à `flock` POSIX aujourd'hui, et tous les écrivains du produit passent par ce chemin unique.
2. **Kill en pleine section critique** peut laisser une dernière ligne JSONL tronquée — exposition préexistante, inchangée par cette décision, et détectée franchement par `verify`.
3. **Contention pathologique > 30 s** se traduit en `LockTimeoutError` — préférable à un blocage infini, observable, et deux ordres de grandeur au-dessus des temps CI observés.
4. **Antivirus/indexeurs Windows** peuvent faire échouer l'`open()` lui-même (sharing violation), hors portée du verrou — échec `OSError` franc et visible, aléa environnemental accepté.
5. **Double chemin d'import** introduit par le repli importlib de `registre.py` — confiné à ce fichier, couvert par le test d'invocation directe, sans effet sur l'import packagé normal.

---

## Amendements de l'orchestrateur (mesurés avant acceptation, 2026-07-30)

**A1 — contrat d'exceptions de la boucle de réessai (l'ADR ne le spécifiait pas).**
Mesure locale POSIX : `flock(LOCK_EX|LOCK_NB)` sur un fichier déjà verrouillé lève
`BlockingIOError` errno=11 (EAGAIN). Documentation Windows : `msvcrt.locking(LK_NBLCK)`
occupé lève `OSError` errno=EACCES. La boucle n'interprète comme « verrou occupé » QUE :
`BlockingIOError` sur POSIX ; `OSError` avec `errno in (EACCES, EDEADLOCK)` sur nt.
TOUTE autre exception (EBADF, EINVAL, ...) PROPAGE immédiatement — un `except OSError` nu
classerait un descripteur invalide comme « occupé » et bouclerait 30 s avant de masquer le
diagnostic réel (leçon : une fonction ne-lève-jamais renvoie la même valeur neutre que le
test soit cassé ou le code buggé).

**A2 — divulgation d'un changement de comportement observable.**
`file_lock` passe de BLOQUANT SANS LIMITE (`flock(LOCK_EX)` actuel, mesuré l.36) à borné
30 s avec `LockTimeoutError`. Assumé (risque n°3 de l'ADR) mais c'est un changement de
contrat pour les appelants de `models/routes.py` : divulgué au pack de revue, jamais
glissé en silence.

**Vérification 3 confirmée par mesure** : en mode « a », une écriture part en fin de fichier
même après `os.lseek(fd, 0)` — le `lseek` du verrou ne peut pas corrompre l'append (POSIX
O_APPEND ; le test CLI multi-processus le prouvera aussi sur Windows en CI).

Décision ACCEPTÉE avec ces amendements. Implémentation en 2 lots : (1) module
`_portable_lock` + ses tests ; (2) migration des deux appelants + adaptation du test de
concurrence + extension du job CI `guard-fs-multi-os`.
