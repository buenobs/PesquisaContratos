from __future__ import annotations

from typing import Protocol

from pesquisacontratos.procurement.models import Contratacao, Documento


class ConectorContratacoes(Protocol):
    nome: str

    def buscar(self, objeto: str, esfera: str | None = None, ano: int | None = None,
               situacao: str | None = None, tipo_contratacao: str | None = None,
               pagina: int = 1) -> list[Contratacao]:
        ...

    def listar_documentos(self, contratacao: Contratacao) -> list[Documento]:
        ...

    def testar_conexao(self) -> tuple[bool, str]:
        """Retorna (ok, mensagem) para o comando `status`."""
        ...
