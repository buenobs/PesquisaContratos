"""Cobertura do downloader, que grava arquivos a partir de dados da API."""
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from pesquisacontratos import db
from pesquisacontratos.procurement import downloader
from pesquisacontratos.procurement.downloader import _slug, baixar_documentos
from pesquisacontratos.procurement.models import Contratacao, Documento


@pytest.fixture
def conn():
    caminho = Path(tempfile.mktemp(suffix=".db"))
    conexao = db.conectar(caminho)
    yield conexao
    conexao.close()
    caminho.unlink(missing_ok=True)


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    destino = tmp_path / "downloads"
    monkeypatch.setattr(downloader, "DOWNLOADS_DIR", destino)
    return destino


@pytest.mark.parametrize("entrada", ["..", ".", "  ..  ", "...", ""])
def test_slug_neutraliza_componentes_que_escapariam_da_pasta(entrada):
    """O nome do órgão vem da API; `..` viraria travessia de caminho."""
    assert _slug(entrada) == "sem_nome"


def test_slug_preserva_nome_normal_e_remove_separadores():
    assert _slug("MINISTERIO DA ECONOMIA") == "MINISTERIO DA ECONOMIA"
    assert "/" not in _slug("00394460005887-1-000019/2025")
    assert "\\" not in _slug("pasta\\subpasta")


def _resposta_stream(conteudo: bytes):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=[conteudo])
    return resp


@patch("pesquisacontratos.procurement.downloader.requests.get")
def test_baixa_e_registra_caminho_local(mock_get, conn, downloads):
    mock_get.return_value = _resposta_stream(b"%PDF-1.4 conteudo")
    contratacao = Contratacao(fonte="pncp", numero_controle="123-1-000019/2025",
                               objeto="x", orgao_nome="MINISTERIO DA ECONOMIA")
    cid = db.upsert_contratacao(conn, contratacao.as_db_dict())

    baixados = baixar_documentos(conn, cid, contratacao,
                                  [Documento("ETP", "https://exemplo/etp.pdf")])

    assert len(baixados) == 1
    assert baixados[0].read_bytes() == b"%PDF-1.4 conteudo"
    # o arquivo tem de ficar dentro de downloads/
    assert downloads.resolve() in baixados[0].resolve().parents

    linha = conn.execute("SELECT caminho_local, baixado_em FROM documentos").fetchone()
    assert linha["caminho_local"] == str(baixados[0])
    assert linha["baixado_em"] is not None


@patch("pesquisacontratos.procurement.downloader.requests.get")
def test_falha_de_rede_registra_documento_sem_caminho(mock_get, conn, downloads):
    mock_get.side_effect = requests.RequestException("timeout")
    contratacao = Contratacao(fonte="pncp", numero_controle="1", objeto="x", orgao_nome="ORGAO")
    cid = db.upsert_contratacao(conn, contratacao.as_db_dict())

    baixados = baixar_documentos(conn, cid, contratacao,
                                  [Documento("ETP", "https://exemplo/etp.pdf")])

    assert baixados == []
    linha = conn.execute("SELECT caminho_local, baixado_em FROM documentos").fetchone()
    assert linha["caminho_local"] is None
    assert linha["baixado_em"] is None  # nada foi baixado, nao pode ter data


@patch("pesquisacontratos.procurement.downloader.requests.get")
def test_uma_falha_nao_impede_os_demais_documentos(mock_get, conn, downloads):
    mock_get.side_effect = [requests.RequestException("falhou"),
                            _resposta_stream(b"%PDF ok")]
    contratacao = Contratacao(fonte="pncp", numero_controle="1", objeto="x", orgao_nome="ORGAO")
    cid = db.upsert_contratacao(conn, contratacao.as_db_dict())

    baixados = baixar_documentos(conn, cid, contratacao, [
        Documento("ETP", "https://exemplo/etp.pdf"),
        Documento("Termo de Referência", "https://exemplo/tr.pdf"),
    ])

    assert len(baixados) == 1
    assert baixados[0].name.startswith("Termo de Refer")


@patch("pesquisacontratos.procurement.downloader.requests.get")
def test_orgao_malicioso_nao_escreve_fora_de_downloads(mock_get, conn, downloads):
    mock_get.return_value = _resposta_stream(b"%PDF")
    contratacao = Contratacao(fonte="pncp", numero_controle="..", objeto="x", orgao_nome="..")
    cid = db.upsert_contratacao(conn, contratacao.as_db_dict())

    baixados = baixar_documentos(conn, cid, contratacao,
                                  [Documento("ETP", "https://exemplo/etp.pdf")])

    assert downloads.resolve() in baixados[0].resolve().parents
