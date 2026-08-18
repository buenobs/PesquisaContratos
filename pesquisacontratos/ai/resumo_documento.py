"""Resume ETP, Termo de Referência ou Matriz de Riscos já baixados (PDF -> texto -> IA)."""
from __future__ import annotations

from pathlib import Path

from pypdf.errors import PyPdfError

from pesquisacontratos.ai.client import perguntar

SISTEMA = (
    "Você resume documentos de contratações públicas brasileiras (ETP, Termo "
    "de Referência ou Matriz de Gerenciamento de Riscos) para um leitor que "
    "precisa entender rapidamente do que se trata. Responda em português, em "
    "tópicos markdown curtos, cobrindo: Objeto, Principais requisitos/critérios "
    "e Riscos identificados (se houver). Seja objetivo, sem repetir o texto "
    "literalmente."
)

MAX_CARACTERES_TEXTO = 12000


def _extrair_texto_pdf(caminho: Path) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(str(caminho))
    partes = [pagina.extract_text() or "" for pagina in leitor.pages]
    return "\n".join(partes).strip()


def resumir_pdf(caminho_pdf: str | Path, forcar: bool = False) -> str:
    """Gera (ou reaproveita do cache em disco) o resumo em IA de um PDF baixado.

    O resumo fica salvo como `<arquivo>.resumo.md` ao lado do PDF, para não
    gastar chamada de API de novo em execuções futuras.
    """
    caminho_pdf = Path(caminho_pdf)
    caminho_resumo = caminho_pdf.with_suffix(caminho_pdf.suffix + ".resumo.md")

    if caminho_resumo.exists() and not forcar:
        return caminho_resumo.read_text(encoding="utf-8")

    try:
        texto = _extrair_texto_pdf(caminho_pdf)
    except (PyPdfError, OSError) as exc:
        # Download truncado ou arquivo que não é PDF: devolve aviso em vez de
        # derrubar o comando (a CLI só trata IANaoConfiguradaError).
        return (f"_Não foi possível ler este PDF ({type(exc).__name__}) — "
                 "o download pode estar corrompido; rode `docs` novamente._")
    if not texto:
        return "_Não foi possível extrair texto deste PDF (pode ser um documento escaneado/imagem)._"

    texto_truncado = texto[:MAX_CARACTERES_TEXTO]
    resumo = perguntar(texto_truncado, sistema=SISTEMA, max_tokens=700)

    caminho_resumo.write_text(resumo, encoding="utf-8")
    return resumo
