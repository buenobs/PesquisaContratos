"""Testes de contrato: batem nas APIs reais e falham quando um campo de que os
conectores dependem muda de nome ou some.

Não rodam na suíte padrão nem no CI (dependem de rede e da disponibilidade dos
portais, e o TCU ainda bloqueia rajadas). Rode de propósito, de tempos em
tempos ou quando uma busca começar a devolver resultado estranho:

    pytest -m contrato -v

Uma falha aqui não é bug no código: é aviso de que o portal mudou e o conector
correspondente precisa ser reajustado.
"""
import datetime as dt

import pytest
import requests

from pesquisacontratos.config import HTTP_TIMEOUT, USER_AGENT
from pesquisacontratos.jurisprudencia import tcu
from pesquisacontratos.procurement import comprasnet, pncp

pytestmark = pytest.mark.contrato

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _campos_ausentes(item: dict, campos: set[str]) -> set[str]:
    return campos - set(item)


def test_pncp_search_mantem_os_campos_usados():
    resp = requests.get(pncp.BASE_SEARCH, headers=HEADERS, timeout=HTTP_TIMEOUT,
                         params={"q": "material", "pagina": 1, "tam_pagina": 5,
                                 "tipos_documento": "edital"})
    resp.raise_for_status()
    itens = resp.json().get("items") or []
    assert itens, "busca do PNCP nao devolveu itens para um termo generico"

    # nomes lidos em pncp._to_contratacao / listar_documentos
    esperados = {"numero_controle_pncp", "ano", "esfera_id", "esfera_nome", "tipo_nome",
                 "orgao_cnpj", "orgao_nome", "uf", "numero_sequencial"}
    ausentes = _campos_ausentes(itens[0], esperados)
    assert not ausentes, f"PNCP deixou de enviar: {sorted(ausentes)}"


def test_pncp_tipos_documento_continua_obrigatorio():
    """Se um dia deixar de ser exigido, o parametro pode sair do conector."""
    sem_param = requests.get(pncp.BASE_SEARCH, headers=HEADERS, timeout=HTTP_TIMEOUT,
                              params={"q": "material", "pagina": 1, "tam_pagina": 5})
    com_param = requests.get(pncp.BASE_SEARCH, headers=HEADERS, timeout=HTTP_TIMEOUT,
                              params={"q": "material", "pagina": 1, "tam_pagina": 5,
                                      "tipos_documento": "edital"})
    com_param.raise_for_status()
    assert com_param.json().get("items"), "busca com tipos_documento parou de devolver itens"
    if sem_param.ok and (sem_param.json().get("items") or []):
        pytest.fail("PNCP voltou a aceitar busca sem tipos_documento — reveja pncp.buscar")


def test_comprasnet_mantem_os_campos_usados():
    hoje = dt.date.today()
    resp = requests.get(comprasnet.BASE_URL, headers=HEADERS, timeout=HTTP_TIMEOUT, params={
        "dataPublicacaoPncpInicial": (hoje - dt.timedelta(days=14)).isoformat(),
        "dataPublicacaoPncpFinal": hoje.isoformat(),
        "codigoModalidade": 5,  # Pregao Eletronico
        "pagina": 1,
        "tamanhoPagina": 5,
    })
    resp.raise_for_status()
    itens = resp.json().get("resultado") or []
    assert itens, "ComprasNet nao devolveu contratacoes nas ultimas 2 semanas"

    # nomes lidos em comprasnet._to_contratacao
    esperados = {"numeroControlePNCP", "objetoCompra", "orgaoEntidadeCnpj",
                 "orgaoEntidadeRazaoSocial", "orgaoEntidadeEsferaId",
                 "tipoInstrumentoConvocatorioNome", "anoCompraPncp",
                 "sequencialCompraPncp", "dataPublicacaoPncp"}
    ausentes = _campos_ausentes(itens[0], esperados)
    assert not ausentes, f"ComprasNet deixou de enviar: {sorted(ausentes)}"


@pytest.mark.parametrize("codigo", comprasnet.MODALIDADES_LICITACAO + comprasnet.MODALIDADES_DIRETA)
def test_comprasnet_codigos_de_modalidade_continuam_validos(codigo):
    """Os codigos 3/5/6/7 foram descobertos por amostragem, nao por documentacao."""
    hoje = dt.date.today()
    resp = requests.get(comprasnet.BASE_URL, headers=HEADERS, timeout=HTTP_TIMEOUT, params={
        "dataPublicacaoPncpInicial": (hoje - dt.timedelta(days=60)).isoformat(),
        "dataPublicacaoPncpFinal": hoje.isoformat(),
        "codigoModalidade": codigo,
        "pagina": 1,
        "tamanhoPagina": 1,
    })
    assert resp.ok, f"modalidade {codigo} passou a ser recusada (HTTP {resp.status_code})"


def test_tcu_sumula_mantem_os_campos_confirmados():
    """`sumula` e a unica base cujos nomes de campo foram confirmados na pratica."""
    cfg = tcu.BASES["sumula"]
    data = tcu._requisitar(cfg["slug"], {"termo": "*", "ordenacao": cfg["ordenacao"],
                                          "quantidade": 5, "inicio": 0, "sinonimos": "true"})
    documentos = data.get("documentos") or []
    assert documentos, "base sumula do TCU nao devolveu documentos"

    esperados = {"KEY", "NUMERO", "ENUNCIADO", "COLEGIADO"}
    ausentes = _campos_ausentes(documentos[0], esperados)
    assert not ausentes, f"base sumula deixou de enviar: {sorted(ausentes)}"


@pytest.mark.parametrize("nome_base", sorted(tcu.BASES))
def test_tcu_todas_as_bases_respondem_e_sao_parseaveis(nome_base):
    """As demais bases tiveram os campos assumidos por analogia; aqui se ve se
    o parse ainda extrai ao menos a chave, que e o identificador no cache."""
    cfg = tcu.BASES[nome_base]
    params = {"termo": "*", "ordenacao": cfg["ordenacao"], "quantidade": 3, "inicio": 0}
    if cfg.get("sinonimos"):
        params["sinonimos"] = "true"
    data = tcu._requisitar(cfg["slug"], params)

    documentos = data.get("documentos") or []
    assert documentos, f"base {nome_base} nao devolveu documentos"
    item = tcu._parse_item(nome_base, cfg["slug"], documentos[0])
    assert item.chave, f"base {nome_base}: nenhum campo KEY reconhecido em _parse_item"
