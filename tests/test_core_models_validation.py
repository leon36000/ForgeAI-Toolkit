"""Validations directes de core/models.py non couvertes par un appelant public :
_memoire_en_mib n'est atteinte en format inattendu que via appel direct (son unique
appelant, _resoudre_ressources, pré-valide déjà le format par regex) ; CapaciteCluster
est un dataclass public dont __post_init__ se teste directement."""
import pytest

from forgeai.core.models import CapaciteCluster, _memoire_en_mib


def test_memoire_en_mib_format_inattendu():
    """_memoire_en_mib est plus permissive que son unique appelant (qui filtre déjà par
    regex ^\\d+(Mi|Gi)$) : ce test verrouille son propre comportement défensif, indépendant
    de tout appelant futur qui ne pré-validerait pas le format."""
    with pytest.raises(ValueError, match="Format mémoire inattendu"):
        _memoire_en_mib("512Ki")


def test_capacite_cluster_refuse_cpu_nul():
    with pytest.raises(ValueError, match="strictement positive"):
        CapaciteCluster(cpu_millicores=0, memoire_mib=1024)


def test_capacite_cluster_refuse_memoire_negative():
    with pytest.raises(ValueError, match="strictement positive"):
        CapaciteCluster(cpu_millicores=1000, memoire_mib=-1)
