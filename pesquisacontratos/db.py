"""Schema SQLite e funções de cache/consulta para os dois módulos (contratações e jurisprudência)."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from pesquisacontratos.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS contratacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte TEXT NOT NULL,
    numero_controle TEXT NOT NULL,
    objeto TEXT,
    orgao_cnpj TEXT,
    orgao_nome TEXT,
    esfera TEXT,
    poder TEXT,
    uf TEXT,
    municipio TEXT,
    modalidade TEXT,
    tipo_contratacao TEXT,
    situacao TEXT,
    ano INTEGER,
    data_publicacao TEXT,
    url_portal TEXT,
    json_bruto TEXT,
    atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (fonte, numero_controle)
);

CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contratacao_id INTEGER NOT NULL REFERENCES contratacoes (id) ON DELETE CASCADE,
    tipo_documento TEXT NOT NULL,
    url_origem TEXT NOT NULL,
    caminho_local TEXT,
    baixado_em TEXT
);

CREATE TABLE IF NOT EXISTS jurisprudencia_tcu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    base TEXT NOT NULL,
    chave TEXT NOT NULL,
    numero TEXT,
    ano TEXT,
    tipo TEXT,
    colegiado TEXT,
    relator TEXT,
    data_sessao TEXT,
    situacao TEXT,
    titulo TEXT,
    sumario TEXT,
    url_pdf TEXT,
    url_doc TEXT,
    url_pesquisa_integrada TEXT,
    resumo_ia TEXT,
    json_bruto TEXT,
    atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (base, chave)
);

CREATE VIRTUAL TABLE IF NOT EXISTS jurisprudencia_fts USING fts5 (
    titulo, sumario, content='jurisprudencia_tcu', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS jurisprudencia_ai AFTER INSERT ON jurisprudencia_tcu BEGIN
    INSERT INTO jurisprudencia_fts (rowid, titulo, sumario)
    VALUES (new.id, new.titulo, new.sumario);
END;

CREATE TRIGGER IF NOT EXISTS jurisprudencia_ad AFTER DELETE ON jurisprudencia_tcu BEGIN
    INSERT INTO jurisprudencia_fts (jurisprudencia_fts, rowid, titulo, sumario)
    VALUES ('delete', old.id, old.titulo, old.sumario);
END;

CREATE TRIGGER IF NOT EXISTS jurisprudencia_au AFTER UPDATE ON jurisprudencia_tcu BEGIN
    INSERT INTO jurisprudencia_fts (jurisprudencia_fts, rowid, titulo, sumario)
    VALUES ('delete', old.id, old.titulo, old.sumario);
    INSERT INTO jurisprudencia_fts (rowid, titulo, sumario)
    VALUES (new.id, new.titulo, new.sumario);
END;
"""


def conectar(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def upsert_contratacao(conn: sqlite3.Connection, dados: dict) -> int:
    campos = [
        "fonte", "numero_controle", "objeto", "orgao_cnpj", "orgao_nome",
        "esfera", "poder", "uf", "municipio", "modalidade", "tipo_contratacao",
        "situacao", "ano", "data_publicacao", "url_portal", "json_bruto",
    ]
    valores = {c: dados.get(c) for c in campos}
    if isinstance(valores.get("json_bruto"), (dict, list)):
        valores["json_bruto"] = json.dumps(valores["json_bruto"], ensure_ascii=False)

    colunas = ", ".join(campos)
    placeholders = ", ".join(f":{c}" for c in campos)
    atualizacoes = ", ".join(f"{c}=excluded.{c}" for c in campos if c not in ("fonte", "numero_controle"))
    sql = f"""
        INSERT INTO contratacoes ({colunas}) VALUES ({placeholders})
        ON CONFLICT (fonte, numero_controle) DO UPDATE SET
            {atualizacoes}, atualizado_em=CURRENT_TIMESTAMP
    """
    conn.execute(sql, valores)
    conn.commit()
    row = conn.execute(
        "SELECT id FROM contratacoes WHERE fonte=? AND numero_controle=?",
        (dados["fonte"], dados["numero_controle"]),
    ).fetchone()
    return row["id"]


def upsert_documento(conn: sqlite3.Connection, contratacao_id: int, tipo_documento: str,
                      url_origem: str, caminho_local: str | None = None) -> None:
    existente = conn.execute(
        "SELECT id FROM documentos WHERE contratacao_id=? AND tipo_documento=? AND url_origem=?",
        (contratacao_id, tipo_documento, url_origem),
    ).fetchone()
    if existente:
        if caminho_local:
            conn.execute(
                "UPDATE documentos SET caminho_local=?, baixado_em=CURRENT_TIMESTAMP WHERE id=?",
                (caminho_local, existente["id"]),
            )
            conn.commit()
        return
    # baixado_em precisa ser a expressão SQL CURRENT_TIMESTAMP, não a string
    # literal — passá-la como parâmetro gravava o texto "CURRENT_TIMESTAMP".
    conn.execute(
        """INSERT INTO documentos (contratacao_id, tipo_documento, url_origem, caminho_local, baixado_em)
           VALUES (?, ?, ?, ?, CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END)""",
        (contratacao_id, tipo_documento, url_origem, caminho_local, caminho_local),
    )
    conn.commit()


def upsert_jurisprudencia(conn: sqlite3.Connection, dados: dict) -> int:
    campos = [
        "base", "chave", "numero", "ano", "tipo", "colegiado", "relator",
        "data_sessao", "situacao", "titulo", "sumario", "url_pdf", "url_doc",
        "url_pesquisa_integrada", "json_bruto",
    ]
    valores = {c: dados.get(c) for c in campos}
    if isinstance(valores.get("json_bruto"), (dict, list)):
        valores["json_bruto"] = json.dumps(valores["json_bruto"], ensure_ascii=False)

    colunas = ", ".join(campos)
    placeholders = ", ".join(f":{c}" for c in campos)
    atualizacoes = ", ".join(f"{c}=excluded.{c}" for c in campos if c not in ("base", "chave"))
    sql = f"""
        INSERT INTO jurisprudencia_tcu ({colunas}) VALUES ({placeholders})
        ON CONFLICT (base, chave) DO UPDATE SET
            {atualizacoes}, atualizado_em=CURRENT_TIMESTAMP
    """
    conn.execute(sql, valores)
    conn.commit()
    row = conn.execute(
        "SELECT id FROM jurisprudencia_tcu WHERE base=? AND chave=?",
        (dados["base"], dados["chave"]),
    ).fetchone()
    return row["id"]


def salvar_resumo_ia_jurisprudencia(conn: sqlite3.Connection, item_id: int, resumo: str) -> None:
    conn.execute("UPDATE jurisprudencia_tcu SET resumo_ia=? WHERE id=?", (resumo, item_id))
    conn.commit()


def _termo_para_fts(termo: str) -> str:
    """Converte texto livre em uma consulta FTS5 segura.

    O FTS5 tem uma sintaxe própria: pontuação, hífen e aspas são operadores, e
    um termo natural como `art. 75` ou `sobrepreço - superfaturamento` faz o
    MATCH lançar OperationalError. Cada palavra vira aqui uma frase entre
    aspas, que o FTS5 combina com AND implícito.
    """
    palavras = re.findall(r"\w+", termo or "", flags=re.UNICODE)
    return " ".join(f'"{p}"' for p in palavras)


def buscar_jurisprudencia_local(conn: sqlite3.Connection, termo: str, limite: int = 50) -> list[sqlite3.Row]:
    """Busca full-text local (fallback quando a API do TCU não tiver dados/estiver indisponível)."""
    consulta = _termo_para_fts(termo)
    if not consulta:
        return []
    sql = """
        SELECT j.* FROM jurisprudencia_tcu j
        JOIN jurisprudencia_fts f ON f.rowid = j.id
        WHERE jurisprudencia_fts MATCH ?
        ORDER BY rank LIMIT ?
    """
    return conn.execute(sql, (consulta, limite)).fetchall()
