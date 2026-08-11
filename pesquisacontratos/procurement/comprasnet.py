"""Conector ComprasNet / Compras.gov.br (Poder Executivo Federal).

API REST pública e sem autenticação (dadosabertos.compras.gov.br), spec
OpenAPI em /v3/api-docs. Usa o endpoint mais moderno, que cobre licitações e
contratações diretas já registradas no PNCP sob a Lei 14.133/2021:

    GET /modulo-contratacoes/1_consultarContratacoes_PNCP_14133

Duas limitações confirmadas na investigação:
1. Não existe parâmetro de busca por texto livre no objeto — `objeto` é
   filtrado no cliente, comparando com `objetoCompra` de cada resultado.
2. `codigoModalidade` é obrigatório e usa uma tabela de códigos própria do
   Compras.gov.br (diferente da tabela de modalidade do PNCP). Os códigos
   abaixo foram confirmados empiricamente consultando a própria API; outros
   códigos legados podem existir mas não foram observados com dados.

Como cada contratação aqui já é publicada no PNCP, os documentos (ETP, TR,
Matriz de Riscos) são buscados reaproveitando o conector `pncp` a partir de
numeroControlePNCP/orgaoEntidadeCnpj/anoCompraPncp/sequencialCompraPncp.
"""
from __future__ import annotations

import datetime as dt

import requests

from pesquisacontratos.config import HTTP_TIMEOUT, USER_AGENT
from pesquisacontratos.procurement import pncp
from pesquisacontratos.procurement.models import Contratacao, Documento

NOME = "comprasnet"

BASE_URL = "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# Códigos de modalidade internos do Compras.gov.br (confirmados por amostragem real).
MODALIDADES_LICITACAO = [3, 5]  # Concorrência Eletrônica, Pregão Eletrônico
MODALIDADES_DIRETA = [6, 7]     # Dispensa, Inexigibilidade

ESFERA_MAP = {"federal": "F", "estadual": "E", "municipal": "M", "distrital": "D"}


def _tipo_contratacao_calculado(item: dict) -> str:
    tipo_nome = (item.get("tipoInstrumentoConvocatorioNome") or "").lower()
    if "edital" in tipo_nome:
        return "licitacao"
    if "contratação direta" in tipo_nome or "dispensa" in tipo_nome or "inexigibilidade" in tipo_nome:
        return "direta"
    return tipo_nome


def _situacao_calculada(item: dict) -> str:
    if item.get("contratacaoExcluida"):
        return "cancelada"
    fim = item.get("dataEncerramentoPropostaPncp")
    if fim:
        try:
            data_fim = dt.datetime.fromisoformat(fim)
            return "em andamento" if data_fim >= dt.datetime.now() else "finalizada"
        except ValueError:
            pass
    return (item.get("situacaoCompraNomePncp") or "").lower()


def _to_contratacao(item: dict) -> Contratacao:
    return Contratacao(
        fonte=NOME,
        numero_controle=item.get("numeroControlePNCP"),
        objeto=item.get("objetoCompra"),
        orgao_cnpj=item.get("orgaoEntidadeCnpj"),
        orgao_nome=item.get("orgaoEntidadeRazaoSocial"),
        esfera={"F": "Federal", "E": "Estadual", "M": "Municipal", "D": "Distrital"}
        .get(item.get("orgaoEntidadeEsferaId"), item.get("orgaoEntidadeEsferaId")),
        poder=item.get("orgaoEntidadePoderId"),
        uf=item.get("unidadeOrgaoUfSigla"),
        municipio=item.get("unidadeOrgaoMunicipioNome"),
        modalidade=item.get("modalidadeNome"),
        tipo_contratacao=_tipo_contratacao_calculado(item),
        situacao=_situacao_calculada(item),
        ano=item.get("anoCompraPncp"),
        data_publicacao=item.get("dataPublicacaoPncp"),
        url_portal=f"https://pncp.gov.br/app/editais/{item.get('orgaoEntidadeCnpj')}/"
                    f"{item.get('anoCompraPncp')}/{item.get('sequencialCompraPncp')}",
        json_bruto=item,
    )


def _modalidades_para(tipo_contratacao: str | None) -> list[int]:
    if tipo_contratacao == "licitacao":
        return MODALIDADES_LICITACAO
    if tipo_contratacao == "direta":
        return MODALIDADES_DIRETA
    return MODALIDADES_LICITACAO + MODALIDADES_DIRETA


def buscar(objeto: str, esfera: str | None = None, ano: int | None = None,
           situacao: str | None = None, tipo_contratacao: str | None = None,
           pagina: int = 1, tam_pagina: int = 50, max_paginas: int = 3) -> list[Contratacao]:
    ano = ano or dt.date.today().year
    data_ini, data_fim = f"{ano}-01-01", f"{ano}-12-31"
    esfera_code = ESFERA_MAP.get((esfera or "").lower())
    objeto_lower = objeto.lower()

    resultados: list[Contratacao] = []
    for codigo_modalidade in _modalidades_para(tipo_contratacao):
        for pg in range(1, max_paginas + 1):
            params = {
                "dataPublicacaoPncpInicial": data_ini,
                "dataPublicacaoPncpFinal": data_fim,
                "codigoModalidade": codigo_modalidade,
                "pagina": pg,
                "tamanhoPagina": tam_pagina,
            }
            resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            itens = resp.json().get("resultado") or []
            if not itens:
                break
            for item in itens:
                if objeto_lower not in (item.get("objetoCompra") or "").lower():
                    continue
                if esfera_code and item.get("orgaoEntidadeEsferaId") != esfera_code:
                    continue
                contratacao = _to_contratacao(item)
                if situacao and situacao.lower() not in (contratacao.situacao or "").lower():
                    continue
                resultados.append(contratacao)
            if len(itens) < tam_pagina:
                break
    return resultados


def listar_documentos(contratacao: Contratacao) -> list[Documento]:
    """Reaproveita o conector PNCP: toda contratação do ComprasNet aqui já está no PNCP."""
    return pncp.listar_documentos(contratacao)


def testar_conexao() -> tuple[bool, str]:
    hoje = dt.date.today()
    inicio = hoje - dt.timedelta(days=7)
    try:
        resp = requests.get(BASE_URL, params={
            "dataPublicacaoPncpInicial": inicio.isoformat(),
            "dataPublicacaoPncpFinal": hoje.isoformat(),
            "codigoModalidade": 5,
            "pagina": 1,
            "tamanhoPagina": 10,
        }, headers=HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        n = len(resp.json().get("resultado") or [])
        return True, f"OK ({n} registros na última semana, modalidade Pregão Eletrônico)"
    except requests.RequestException as exc:
        return False, f"Erro: {exc}"
