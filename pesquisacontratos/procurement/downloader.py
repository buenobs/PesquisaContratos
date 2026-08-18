from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import requests

from pesquisacontratos.config import DOWNLOADS_DIR, HTTP_TIMEOUT, USER_AGENT
from pesquisacontratos.db import upsert_documento
from pesquisacontratos.procurement.models import Contratacao, Documento

HEADERS = {"User-Agent": USER_AGENT}


def _slug(texto: str) -> str:
    """Transforma um nome vindo da API em um componente de caminho seguro."""
    texto = re.sub(r"[^\w\-. ]+", "_", texto or "", flags=re.UNICODE).strip()[:120]
    # "." e ".." sobrevivem ao filtro acima (o ponto é permitido) e, como
    # componente de caminho, escapariam de downloads/. O nome do órgão vem da
    # API, então não é dado confiável.
    if not texto or set(texto) <= {"."}:
        return "sem_nome"
    return texto


def baixar_documentos(conn: sqlite3.Connection, contratacao_id: int, contratacao: Contratacao,
                       documentos: list[Documento]) -> list[Path]:
    pasta = DOWNLOADS_DIR / _slug(contratacao.orgao_nome or contratacao.orgao_cnpj or "orgao") \
        / _slug(contratacao.numero_controle)
    pasta.mkdir(parents=True, exist_ok=True)

    baixados = []
    for doc in documentos:
        destino = pasta / f"{_slug(doc.tipo_documento)}.pdf"
        try:
            resp = requests.get(doc.url_origem, headers=HEADERS, timeout=HTTP_TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(destino, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
        except requests.RequestException:
            upsert_documento(conn, contratacao_id, doc.tipo_documento, doc.url_origem, None)
            continue
        upsert_documento(conn, contratacao_id, doc.tipo_documento, doc.url_origem, str(destino))
        baixados.append(destino)
    return baixados
