"""Regressões dos bugs encontrados na revisão do projeto."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.table import Table

from pesquisacontratos import db
from pesquisacontratos.cli import _celula, _tabela_contratacoes
from pesquisacontratos.jurisprudencia import tcu
from pesquisacontratos.procurement import pncp
from pesquisacontratos.procurement.models import Contratacao


@pytest.fixture
def conn():
    caminho = Path(tempfile.mktemp(suffix=".db"))
    conexao = db.conectar(caminho)
    yield conexao
    conexao.close()
    caminho.unlink(missing_ok=True)


def test_baixado_em_grava_timestamp_e_nao_a_string_literal(conn):
    cid = db.upsert_contratacao(conn, {"fonte": "pncp", "numero_controle": "1", "objeto": "x"})
    db.upsert_documento(conn, cid, "ETP", "https://exemplo/etp.pdf", "/tmp/etp.pdf")

    baixado_em = conn.execute("SELECT baixado_em FROM documentos").fetchone()["baixado_em"]
    assert baixado_em != "CURRENT_TIMESTAMP"
    assert baixado_em.startswith("20")  # data real, ex.: "2026-08-17 12:34:56"


def test_baixado_em_fica_nulo_quando_download_falha(conn):
    cid = db.upsert_contratacao(conn, {"fonte": "pncp", "numero_controle": "1", "objeto": "x"})
    db.upsert_documento(conn, cid, "ETP", "https://exemplo/etp.pdf", None)

    assert conn.execute("SELECT baixado_em FROM documentos").fetchone()["baixado_em"] is None


@pytest.mark.parametrize("termo", ["art. 75", "sobrepreço - superfaturamento",
                                     'aspas "soltas"', "(parcelamento)", "  "])
def test_busca_local_aceita_pontuacao_sem_quebrar(conn, termo):
    """Texto livre não pode vazar como sintaxe do FTS5 (era OperationalError)."""
    db.upsert_jurisprudencia(conn, {
        "base": "acordao", "chave": "A-1", "titulo": "Parcelamento do objeto",
        "sumario": "art. 75 trata de sobrepreço e superfaturamento",
    })

    db.buscar_jurisprudencia_local(conn, termo)  # não deve lançar


def test_busca_local_ainda_encontra_por_multiplas_palavras(conn):
    db.upsert_jurisprudencia(conn, {
        "base": "acordao", "chave": "A-1", "titulo": "Parcelamento do objeto",
        "sumario": "trata de fracionamento de despesa",
    })
    db.upsert_jurisprudencia(conn, {
        "base": "sumula", "chave": "S-1", "titulo": "Exclusividade",
        "sumario": "contratação direta por inexigibilidade",
    })

    assert len(db.buscar_jurisprudencia_local(conn, "parcelamento, objeto!")) == 1
    assert db.buscar_jurisprudencia_local(conn, "!!!") == []


@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_bloqueio_total_propaga_para_acionar_fallback_local(mock_get, _sleep):
    """Se nenhuma base responde, buscar() precisa propagar — é o que dispara o
    fallback para o cache local na CLI (antes era engolido e virava lista vazia)."""
    bloqueada = MagicMock()
    bloqueada.status_code = 200
    bloqueada.json.side_effect = ValueError("pagina HTML do firewall")
    mock_get.return_value = bloqueada

    with pytest.raises(tcu.TCUBloqueadoError):
        tcu.buscar("qualquer", base="sumula")


@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_bloqueio_parcial_nao_propaga(mock_get, _sleep):
    """Uma base bloqueada não pode derrubar as demais."""
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"documentos": [{"KEY": "S-1", "NUMERO": "255"}]}
    bloqueada = MagicMock()
    bloqueada.status_code = 200
    bloqueada.json.side_effect = ValueError("pagina HTML do firewall")
    # 1ª base responde; a 2ª esgota as 3 tentativas bloqueada.
    mock_get.side_effect = [ok] + [bloqueada] * 3

    duas_bases = {nome: tcu.BASES[nome] for nome in ("sumula", "acordao")}
    with patch.dict(tcu.BASES, duas_bases, clear=True):
        resultados = tcu.buscar("x")

    assert len(resultados) == 1
    assert resultados[0].base == "sumula"


def _renderizar(tabela: Table) -> str:
    console = Console(width=200)
    with console.capture() as cap:
        console.print(tabela)
    return cap.get()


def test_tabela_nao_quebra_com_markup_vindo_da_api():
    """Objeto de licitação com `[/...]` derrubava o comando com MarkupError."""
    resultados = [
        Contratacao(fonte="pncp", numero_controle="1/2025",
                     objeto="Material [LOTE 1] e fecha [/bold] solto", orgao_nome="ORGAO [X]"),
    ]

    saida = _renderizar(_tabela_contratacoes(resultados))

    assert "[LOTE 1]" in saida  # texto preservado, não interpretado como estilo
    assert "[/bold]" in saida


def test_celula_preserva_texto_e_usa_padrao_para_vazio():
    assert _celula("Anexo [I]").plain == "Anexo [I]"
    assert _celula(None).plain == "-"
    assert _celula("   ").plain == "-"


def _resposta(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_buscar_pagina_ate_achar_itens_filtrados(mock_get):
    """Filtros são client-side: parar na 1ª página escondia resultados válidos."""
    de_2024 = {"ano": "2024", "tipo_nome": "Edital", "numero_controle_pncp": "antigo",
               "esfera_id": "F", "description": "x"}
    de_2025 = {"ano": "2025", "tipo_nome": "Edital", "numero_controle_pncp": "novo",
               "esfera_id": "F", "description": "x"}
    # página cheia (tam_pagina=2) só com itens de 2024; o alvo está na 2ª página
    mock_get.side_effect = [
        _resposta({"items": [de_2024, de_2024]}),
        _resposta({"items": [de_2025]}),
    ]

    resultados = pncp.buscar("x", ano=2025, tam_pagina=2)

    assert [r.numero_controle for r in resultados] == ["novo"]
    assert mock_get.call_count == 2


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_buscar_para_na_pagina_incompleta(mock_get):
    mock_get.return_value = _resposta({"items": [{"ano": "2025", "tipo_nome": "Edital",
                                                    "numero_controle_pncp": "a", "esfera_id": "F",
                                                    "description": "x"}]})

    pncp.buscar("x", tam_pagina=20)

    assert mock_get.call_count == 1  # não desperdiça chamadas


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_listar_documentos_ignora_arquivo_sem_url(mock_get):
    contratacao = Contratacao(fonte="pncp", numero_controle="1", objeto="x",
                               orgao_cnpj="00394460005887", ano=2025,
                               json_bruto={"numero_sequencial": "19"})
    mock_get.return_value = _resposta([
        {"tipoDocumentoId": 7},  # ETP sem url/uri
        {"tipoDocumentoId": 4, "url": "https://exemplo/tr.pdf"},
    ])

    documentos = pncp.listar_documentos(contratacao)

    assert [d.tipo_documento for d in documentos] == ["Termo de Referência"]
    assert all(d.url_origem for d in documentos)
