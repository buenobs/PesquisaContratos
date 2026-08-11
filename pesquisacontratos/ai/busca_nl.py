"""Interpreta uma necessidade em linguagem natural e sugere filtros de busca
para o módulo de contratações (pesquisacontratos.procurement)."""
from __future__ import annotations

import json

from pesquisacontratos.ai.client import perguntar

ESFERAS_VALIDAS = {"federal", "estadual", "municipal", "distrital"}
TIPOS_VALIDOS = {"licitacao", "direta"}

SISTEMA = (
    "Você extrai parâmetros de busca de contratações públicas brasileiras a "
    "partir de um pedido em linguagem natural. Responda APENAS com um JSON "
    "no formato exato: "
    '{"objeto": "termos de busca curtos e objetivos, sem enrolação", '
    '"esfera": "federal" | "estadual" | "municipal" | "distrital" | null, '
    '"tipo_contratacao": "licitacao" | "direta" | null}. '
    "Use null quando o pedido não deixar claro esfera ou tipo. "
    "Não invente órgão nem ano."
)


def interpretar(texto_livre: str) -> dict:
    """Retorna {"objeto": str, "esfera": str|None, "tipo_contratacao": str|None}.

    Em caso de falha na IA (não configurada, erro de rede, JSON inválido),
    cai de volta para uma busca literal pelo texto informado — nunca lança
    exceção para quem chama.
    """
    fallback = {"objeto": texto_livre.strip(), "esfera": None, "tipo_contratacao": None}
    try:
        resposta = perguntar(texto_livre, sistema=SISTEMA, json_mode=True, max_tokens=200)
        dados = json.loads(resposta)
    except Exception:
        return fallback

    objeto = (dados.get("objeto") or "").strip() or fallback["objeto"]
    esfera = str(dados.get("esfera") or "").strip().lower() or None
    if esfera not in ESFERAS_VALIDAS:
        esfera = None
    tipo = str(dados.get("tipo_contratacao") or "").strip().lower() or None
    if tipo not in TIPOS_VALIDOS:
        tipo = None

    return {"objeto": objeto, "esfera": esfera, "tipo_contratacao": tipo}
