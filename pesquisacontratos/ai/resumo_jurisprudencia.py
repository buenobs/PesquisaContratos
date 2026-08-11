"""Resume acórdãos/súmulas do TCU em linguagem simples, complementando a ementa oficial."""
from __future__ import annotations

from pesquisacontratos.ai.client import perguntar
from pesquisacontratos.jurisprudencia.models import ItemJurisprudencia

SISTEMA = (
    "Você explica, em português simples e direto (2 a 4 frases), decisões e "
    "súmulas do Tribunal de Contas da União para alguém sem formação jurídica. "
    "Não repita a ementa literalmente — explique o que ela significa na prática."
)


def resumir(item: ItemJurisprudencia) -> str:
    base_texto = item.sumario or item.titulo or ""
    if not base_texto.strip():
        return "_Sem ementa/sumário disponível para resumir._"

    prompt = f"Tipo: {item.tipo or item.base}\nTexto oficial:\n{base_texto}"
    return perguntar(prompt, sistema=SISTEMA, max_tokens=300)
