"""Conector PNCP (Portal Nacional de Contratações Públicas).

Usa dois serviços públicos, sem autenticação:
- /api/search: mesma busca por texto livre usada pelo site do PNCP.
- /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos: lista os
  documentos (edital, ETP, Termo de Referência, Matriz de Riscos etc.) de
  uma compra específica, tipados por `tipoDocumentoId`.

Os parâmetros de filtro server-side (esfera, status, ano) da busca por texto
não têm nomes oficialmente documentados e nem sempre são respeitados pela
API; por isso a filtragem real acontece no cliente, comparando os campos
devolvidos em cada item (esfera_id, tipo_nome, ano, datas de vigência).
"""
from __future__ import annotations

import datetime as dt

import requests

from pesquisacontratos.config import HTTP_TIMEOUT, USER_AGENT
from pesquisacontratos.procurement.models import Contratacao, Documento

NOME = "pncp"

BASE_SEARCH = "https://pncp.gov.br/api/search/"
BASE_ARQUIVOS = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos"

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

ESFERA_MAP = {"federal": "F", "estadual": "E", "municipal": "M", "distrital": "D"}

# tipoDocumentoId conforme Manual de Integração PNCP (item 5.12 - Tipo de Documento)
TIPOS_DOCUMENTO_INTERESSE = {
    4: "Termo de Referência",
    7: "ETP",
    9: "Matriz de Riscos",
}

TIPO_LICITACAO_PALAVRAS = ("edital",)
TIPO_DIRETA_PALAVRAS = ("contratação direta", "dispensa", "inexigibilidade")


def _situacao_calculada(item: dict) -> str:
    """PNCP não expõe diretamente 'em andamento'/'finalizada'; deriva pela
    data de fim de vigência das propostas quando disponível."""
    if item.get("cancelado"):
        return "cancelada"
    fim = item.get("data_fim_vigencia")
    if fim:
        try:
            data_fim = dt.datetime.fromisoformat(fim)
            agora = dt.datetime.now(data_fim.tzinfo) if data_fim.tzinfo else dt.datetime.now()
            return "em andamento" if data_fim >= agora else "finalizada"
        except ValueError:
            pass
    return (item.get("situacao_nome") or "").lower()


def _tipo_contratacao_calculado(item: dict) -> str:
    tipo_nome = (item.get("tipo_nome") or "").lower()
    if any(p in tipo_nome for p in TIPO_LICITACAO_PALAVRAS):
        return "licitacao"
    if any(p in tipo_nome for p in TIPO_DIRETA_PALAVRAS):
        return "direta"
    return tipo_nome


def _to_contratacao(item: dict) -> Contratacao:
    return Contratacao(
        fonte=NOME,
        numero_controle=item.get("numero_controle_pncp") or item.get("id"),
        objeto=item.get("description") or item.get("title"),
        orgao_cnpj=item.get("orgao_cnpj"),
        orgao_nome=item.get("orgao_nome"),
        esfera=item.get("esfera_nome"),
        poder=item.get("poder_nome"),
        uf=item.get("uf"),
        municipio=item.get("municipio_nome"),
        modalidade=item.get("modalidade_licitacao_nome"),
        tipo_contratacao=_tipo_contratacao_calculado(item),
        situacao=_situacao_calculada(item),
        ano=int(item["ano"]) if item.get("ano") else None,
        data_publicacao=item.get("data_publicacao_pncp"),
        url_portal=f"https://pncp.gov.br/app/editais{item.get('item_url', '')}"
        if item.get("item_url") else None,
        json_bruto=item,
    )


def buscar(objeto: str, esfera: str | None = None, ano: int | None = None,
           situacao: str | None = None, tipo_contratacao: str | None = None,
           pagina: int = 1, tam_pagina: int = 20, max_paginas: int = 3) -> list[Contratacao]:
    resultados: list[Contratacao] = []
    esfera_code = ESFERA_MAP.get((esfera or "").lower())

    # Como ano/situação/tipo são filtrados no cliente (a API não os respeita de
    # forma confiável), varrer só a primeira página faz uma busca com filtros
    # devolver 0 resultados mesmo havendo correspondências logo adiante.
    for pg in range(pagina, pagina + max_paginas):
        # tipos_documento é obrigatório na API; "edital" cobre tanto licitações
        # quanto avisos de contratação direta (confirmado empiricamente — o
        # campo tipo_nome de cada item é que distingue os dois, não este filtro).
        params = {"q": objeto, "pagina": pg, "tam_pagina": tam_pagina,
                  "tipos_documento": "edital"}
        if esfera:
            params["esfera"] = ESFERA_MAP.get(esfera.lower(), esfera)

        resp = requests.get(BASE_SEARCH, params=params, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        itens = resp.json().get("items") or []
        if not itens:
            break

        for item in itens:
            if ano and str(item.get("ano")) != str(ano):
                continue
            if esfera_code and item.get("esfera_id") != esfera_code:
                continue
            contratacao = _to_contratacao(item)
            if situacao and situacao.lower() not in (contratacao.situacao or "").lower():
                continue
            if tipo_contratacao and tipo_contratacao.lower() != (contratacao.tipo_contratacao or "").lower():
                continue
            resultados.append(contratacao)

        if len(itens) < tam_pagina:  # última página
            break
    return resultados


def listar_documentos(contratacao: Contratacao) -> list[Documento]:
    item = contratacao.json_bruto or {}
    cnpj = contratacao.orgao_cnpj
    ano = contratacao.ano
    sequencial = item.get("numero_sequencial")
    if not (cnpj and ano and sequencial):
        return []

    url = BASE_ARQUIVOS.format(cnpj=cnpj, ano=ano, sequencial=sequencial)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        arquivos = resp.json()
    except (requests.RequestException, ValueError):
        return []

    documentos = []
    for arq in arquivos:
        tipo_id = arq.get("tipoDocumentoId")
        if tipo_id not in TIPOS_DOCUMENTO_INTERESSE:
            continue
        url = arq.get("url") or arq.get("uri")
        if not url:  # sem URL não há o que baixar; deixar passar quebraria o downloader
            continue
        documentos.append(Documento(
            tipo_documento=TIPOS_DOCUMENTO_INTERESSE[tipo_id],
            url_origem=url,
        ))
    return documentos


def testar_conexao() -> tuple[bool, str]:
    try:
        resp = requests.get(BASE_SEARCH, params={"q": "teste", "pagina": 1, "tam_pagina": 1,
                                                   "tipos_documento": "edital"},
                             headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        total = resp.json().get("total", "?")
        return True, f"OK ({total} registros no índice)"
    except requests.RequestException as exc:
        return False, f"Erro: {exc}"
