"""O diretório de dados não pode cair dentro do site-packages."""
from pathlib import Path

from pesquisacontratos.config import _diretorio_base


def test_variavel_de_ambiente_tem_prioridade(monkeypatch, tmp_path):
    monkeypatch.setenv("PESQUISACONTRATOS_DIR", str(tmp_path / "meus-dados"))

    assert _diretorio_base() == (tmp_path / "meus-dados").resolve()


def test_usa_a_raiz_do_repositorio_em_checkout(monkeypatch):
    monkeypatch.delenv("PESQUISACONTRATOS_DIR", raising=False)
    raiz_repo = Path(__file__).resolve().parent.parent

    # o checkout tem pyproject.toml na raiz; é o que sinaliza uso em dev
    assert (raiz_repo / "pyproject.toml").is_file()
    assert _diretorio_base() == raiz_repo


def test_fora_de_checkout_grava_em_diretorio_do_usuario(monkeypatch, tmp_path):
    """Simula instalação normal: sem pyproject.toml ao lado do pacote."""
    monkeypatch.delenv("PESQUISACONTRATOS_DIR", raising=False)
    monkeypatch.setattr("pesquisacontratos.config.Path.is_file", lambda self: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    destino = _diretorio_base()

    assert destino == tmp_path / "PesquisaContratos"
    assert "site-packages" not in str(destino)
