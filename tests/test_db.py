import tempfile
from pathlib import Path

from pesquisacontratos import db


def _db_temporario():
    caminho = Path(tempfile.mktemp(suffix=".db"))
    conn = db.conectar(caminho)
    return conn, caminho


def test_upsert_contratacao_cria_e_atualiza():
    conn, caminho = _db_temporario()
    try:
        dados = {
            "fonte": "pncp", "numero_controle": "123-1-000001/2025",
            "objeto": "compra de veiculos", "esfera": "Federal", "ano": 2025,
            "situacao": "em andamento", "tipo_contratacao": "licitacao",
        }
        id1 = db.upsert_contratacao(conn, dados)
        dados["situacao"] = "finalizada"
        id2 = db.upsert_contratacao(conn, dados)

        assert id1 == id2
        row = conn.execute("SELECT * FROM contratacoes WHERE id=?", (id1,)).fetchone()
        assert row["situacao"] == "finalizada"
        assert conn.execute("SELECT COUNT(*) c FROM contratacoes").fetchone()["c"] == 1
    finally:
        conn.close()
        caminho.unlink(missing_ok=True)


def test_upsert_documento_nao_duplica():
    conn, caminho = _db_temporario()
    try:
        cid = db.upsert_contratacao(conn, {"fonte": "pncp", "numero_controle": "1", "objeto": "x"})
        db.upsert_documento(conn, cid, "ETP", "https://exemplo/etp.pdf", None)
        db.upsert_documento(conn, cid, "ETP", "https://exemplo/etp.pdf", "/tmp/etp.pdf")

        docs = conn.execute("SELECT * FROM documentos WHERE contratacao_id=?", (cid,)).fetchall()
        assert len(docs) == 1
        assert docs[0]["caminho_local"] == "/tmp/etp.pdf"
    finally:
        conn.close()
        caminho.unlink(missing_ok=True)


def test_busca_jurisprudencia_local_fts5():
    conn, caminho = _db_temporario()
    try:
        db.upsert_jurisprudencia(conn, {
            "base": "acordao", "chave": "ACORDAO-1", "titulo": "Parcelamento do objeto",
            "sumario": "Trata de fracionamento de despesa em licitacoes publicas",
        })
        db.upsert_jurisprudencia(conn, {
            "base": "sumula", "chave": "SUMULA-1", "titulo": "Súmula sobre exclusividade",
            "sumario": "Trata de contratacao direta por inexigibilidade",
        })

        resultados = db.buscar_jurisprudencia_local(conn, "parcelamento")
        assert len(resultados) == 1
        assert resultados[0]["chave"] == "ACORDAO-1"
    finally:
        conn.close()
        caminho.unlink(missing_ok=True)
