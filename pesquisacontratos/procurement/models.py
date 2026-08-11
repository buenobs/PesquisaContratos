from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Documento:
    tipo_documento: str  # "ETP" | "Termo de Referência" | "Matriz de Riscos"
    url_origem: str
    caminho_local: str | None = None


@dataclass
class Contratacao:
    fonte: str  # "pncp" | "comprasnet"
    numero_controle: str
    objeto: str
    orgao_cnpj: str | None = None
    orgao_nome: str | None = None
    esfera: str | None = None
    poder: str | None = None
    uf: str | None = None
    municipio: str | None = None
    modalidade: str | None = None
    tipo_contratacao: str | None = None  # "licitacao" | "direta"
    situacao: str | None = None
    ano: int | None = None
    data_publicacao: str | None = None
    url_portal: str | None = None
    documentos: list[Documento] = field(default_factory=list)
    json_bruto: dict | None = None

    def as_db_dict(self) -> dict:
        return {
            "fonte": self.fonte,
            "numero_controle": self.numero_controle,
            "objeto": self.objeto,
            "orgao_cnpj": self.orgao_cnpj,
            "orgao_nome": self.orgao_nome,
            "esfera": self.esfera,
            "poder": self.poder,
            "uf": self.uf,
            "municipio": self.municipio,
            "modalidade": self.modalidade,
            "tipo_contratacao": self.tipo_contratacao,
            "situacao": self.situacao,
            "ano": self.ano,
            "data_publicacao": self.data_publicacao,
            "url_portal": self.url_portal,
            "json_bruto": self.json_bruto,
        }
