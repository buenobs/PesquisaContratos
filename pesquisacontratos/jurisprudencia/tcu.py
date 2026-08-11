"""Conector de jurisprudência do TCU.

Endpoint confirmado por inspeção de rede da Pesquisa Integrada do TCU
(pesquisa.apps.tcu.gov.br), público e sem autenticação:

    GET https://pesquisa.apps.tcu.gov.br/rest/publico/base/{slug}/documentosResumidos
        ?termo={termo}&ordenacao={campos}&quantidade={n}&inicio={offset}[&sinonimos=true]

Resposta: {"quantidadeEncontrada": N, "inicio": 0, "documentos": [...]}.
Os nomes de campo dentro de "documentos" variam por base (todos em
MAIÚSCULAS, ex.: KEY, TIPO, TITULO, NUMERO, ENUNCIADO/SUMARIO, COLEGIADO) —
o mapeamento abaixo foi confirmado para a base `sumula` e é aplicado por
analogia às demais; ajuste os nomes de campo em `_pick(...)` caso alguma
base específica devolva chaves diferentes na prática.

IMPORTANTE: o endpoint é protegido por um firewall de aplicação que bloqueia
rajadas de requisições (confirmado experimentalmente: poucas chamadas em
menos de 1 segundo já disparam bloqueio temporário, com a resposta virando
uma página HTML "Requisição rejeitada" em vez do JSON esperado). Por isso
este módulo:
- espaça as chamadas (mínimo ~1,5s entre requisições);
- detecta a página de bloqueio e recua (backoff) antes de tentar de novo;
- nunca dispara chamadas em paralelo para essa API.
"""
from __future__ import annotations

import time

import requests

from pesquisacontratos.config import HTTP_TIMEOUT, USER_AGENT
from pesquisacontratos.jurisprudencia.models import ItemJurisprudencia

NOME = "tcu"

BASE_URL = "https://pesquisa.apps.tcu.gov.br/rest/publico/base/{slug}/documentosResumidos"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json",
           "Referer": "https://pesquisa.apps.tcu.gov.br/"}

INTERVALO_MINIMO_SEGUNDOS = 1.5

BASES = {
    "acordao": {
        "slug": "acordao-completo",
        "ordenacao": "DTRELEVANCIA desc, NUMACORDAOINT desc, COPIACOLEGIADO desc, KEY asc",
    },
    "sumula": {
        "slug": "sumula",
        "ordenacao": "DTRELEVANCIA desc, NUMEROINT desc, KEY asc",
        "sinonimos": True,
    },
    "jurisprudencia_selecionada": {
        "slug": "jurisprudencia-selecionada",
        "ordenacao": "score desc, COLEGIADO asc, ANOACORDAO desc, NUMACORDAO desc, KEY asc",
        "sinonimos": True,
    },
    "publicacao": {
        "slug": "publicacao",
        "ordenacao": "DTRELEVANCIA desc, KEY asc",
    },
    "resposta_consulta": {
        "slug": "resposta-consulta",
        "ordenacao": "score desc, COLEGIADO asc, ANOACORDAO desc, NUMACORDAO desc, KEY asc",
        "sinonimos": True,
    },
}


class TCUBloqueadoError(Exception):
    """O firewall de aplicação do TCU recusou as requisições nesta janela de tempo."""


_ultima_chamada = 0.0


def _pausar_se_necessario() -> None:
    global _ultima_chamada
    decorrido = time.time() - _ultima_chamada
    if decorrido < INTERVALO_MINIMO_SEGUNDOS:
        time.sleep(INTERVALO_MINIMO_SEGUNDOS - decorrido)


def _requisitar(slug: str, params: dict, tentativas: int = 3) -> dict:
    global _ultima_chamada
    url = BASE_URL.format(slug=slug)
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        _pausar_se_necessario()
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=HTTP_TIMEOUT)
        finally:
            _ultima_chamada = time.time()
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                pass  # provavelmente a página HTML de bloqueio do firewall
        ultimo_erro = RuntimeError(f"HTTP {resp.status_code} para {slug}")
        time.sleep(2 * tentativa)
    raise TCUBloqueadoError(
        "TCU bloqueou temporariamente as requisições (firewall de aplicação). "
        "Aguarde alguns minutos e tente novamente."
    ) from ultimo_erro


def _pick(doc: dict, *candidatos: str):
    for c in candidatos:
        for chave in (c, c.upper(), c.lower()):
            if chave in doc and doc[chave] not in (None, ""):
                return doc[chave]
    return None


def _parse_item(base: str, slug: str, doc: dict) -> ItemJurisprudencia:
    chave = _pick(doc, "KEY")
    return ItemJurisprudencia(
        base=base,
        chave=chave,
        numero=_pick(doc, "NUMERO", "NUMEROACORDAO", "NUMACORDAO"),
        ano=_pick(doc, "ANOACORDAO", "ANOAPROVACAO", "ANO"),
        tipo=_pick(doc, "TIPO"),
        colegiado=_pick(doc, "COLEGIADO"),
        relator=_pick(doc, "RELATOR", "AUTORTESE"),
        data_sessao=_pick(doc, "DATASESSAO", "DTSESSAO", "DTATUALIZACAO"),
        situacao=_pick(doc, "SITUACAO", "VIGENTE"),
        titulo=_pick(doc, "TITULO"),
        sumario=_pick(doc, "SUMARIO", "ENUNCIADO", "CABECALHO"),
        url_pdf=_pick(doc, "URLARQUIVOPDF", "URLPDF"),
        url_doc=_pick(doc, "URLARQUIVO", "URLDOC"),
        url_pesquisa_integrada=(
            f"https://pesquisa.apps.tcu.gov.br/documento/{slug}/{chave}" if chave else None
        ),
        json_bruto=doc,
    )


def buscar(termo: str, base: str | None = None, ano: int | None = None,
           relator: str | None = None, colegiado: str | None = None,
           quantidade: int = 20) -> list[ItemJurisprudencia]:
    bases = [base] if base else list(BASES.keys())
    resultados: list[ItemJurisprudencia] = []
    for nome_base in bases:
        cfg = BASES[nome_base]
        params = {
            "termo": termo or "*",
            "ordenacao": cfg["ordenacao"],
            "quantidade": quantidade,
            "inicio": 0,
        }
        if cfg.get("sinonimos"):
            params["sinonimos"] = "true"
        try:
            data = _requisitar(cfg["slug"], params)
        except TCUBloqueadoError:
            continue
        for doc in data.get("documentos", []):
            item = _parse_item(nome_base, cfg["slug"], doc)
            if ano and item.ano and str(ano) != str(item.ano):
                continue
            if relator and relator.lower() not in (item.relator or "").lower():
                continue
            if colegiado and colegiado.lower() not in (item.colegiado or "").lower():
                continue
            resultados.append(item)
    return resultados


def testar_conexao() -> tuple[bool, str]:
    try:
        data = _requisitar(BASES["acordao"]["slug"], {
            "termo": "*", "ordenacao": BASES["acordao"]["ordenacao"], "quantidade": 1, "inicio": 0,
        })
        return True, f"OK ({data.get('quantidadeEncontrada', '?')} acórdãos no índice)"
    except TCUBloqueadoError as exc:
        return False, str(exc)
