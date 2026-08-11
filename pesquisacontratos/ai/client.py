"""Cliente para a API gratuita da Nvidia (NIM), compatível com o formato OpenAI."""
from __future__ import annotations

from pesquisacontratos.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL, ia_configurada


class IANaoConfiguradaError(Exception):
    """NVIDIA_API_KEY não definida no .env."""


def perguntar(prompt: str, sistema: str | None = None, json_mode: bool = False,
               max_tokens: int = 800) -> str:
    if not ia_configurada():
        raise IANaoConfiguradaError(
            "IA não configurada — defina NVIDIA_API_KEY no arquivo .env "
            "(chave gratuita em https://build.nvidia.com)."
        )
    from openai import OpenAI  # import tardio: só é necessário quando a IA é usada

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    mensagens = []
    if sistema:
        mensagens.append({"role": "system", "content": sistema})
    mensagens.append({"role": "user", "content": prompt})

    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resposta = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=mensagens,
        max_tokens=max_tokens,
        temperature=0.2,
        **kwargs,
    )
    return resposta.choices[0].message.content or ""
