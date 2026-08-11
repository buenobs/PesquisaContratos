from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ItemJurisprudencia:
    base: str  # "acordao" | "sumula" | "jurisprudencia_selecionada" | "publicacao" | "resposta_consulta"
    chave: str
    numero: str | None = None
    ano: str | None = None
    tipo: str | None = None
    colegiado: str | None = None
    relator: str | None = None
    data_sessao: str | None = None
    situacao: str | None = None
    titulo: str | None = None
    sumario: str | None = None
    url_pdf: str | None = None
    url_doc: str | None = None
    url_pesquisa_integrada: str | None = None
    json_bruto: dict | None = None

    def as_db_dict(self) -> dict:
        return {
            "base": self.base,
            "chave": self.chave,
            "numero": self.numero,
            "ano": self.ano,
            "tipo": self.tipo,
            "colegiado": self.colegiado,
            "relator": self.relator,
            "data_sessao": self.data_sessao,
            "situacao": self.situacao,
            "titulo": self.titulo,
            "sumario": self.sumario,
            "url_pdf": self.url_pdf,
            "url_doc": self.url_doc,
            "url_pesquisa_integrada": self.url_pesquisa_integrada,
            "json_bruto": self.json_bruto,
        }
