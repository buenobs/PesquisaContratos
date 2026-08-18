"""Cobertura do cliente de IA e dos dois resumos."""
from unittest.mock import patch

import pytest

from pesquisacontratos.ai import client, resumo_documento
from pesquisacontratos.ai.client import IANaoConfiguradaError, perguntar
from pesquisacontratos.ai.resumo_documento import resumir_pdf
from pesquisacontratos.ai.resumo_jurisprudencia import resumir
from pesquisacontratos.jurisprudencia.models import ItemJurisprudencia


def test_sem_chave_configurada_erro_e_explicito(monkeypatch):
    monkeypatch.setattr(client, "ia_configurada", lambda: False)

    with pytest.raises(IANaoConfiguradaError, match="NVIDIA_API_KEY"):
        perguntar("qualquer coisa")


def test_pdf_corrompido_vira_aviso_em_vez_de_excecao(tmp_path):
    """cli.resumir_docs so trata IANaoConfiguradaError: um PDF truncado
    derrubava o comando inteiro."""
    ruim = tmp_path / "truncado.pdf"
    ruim.write_bytes(b"isto nao e um PDF")

    resultado = resumir_pdf(ruim)

    assert "não foi possível ler" in resultado.lower()
    assert not (tmp_path / "truncado.pdf.resumo.md").exists()  # erro nao vira cache


def test_pdf_vazio_tambem_e_tratado(tmp_path):
    vazio = tmp_path / "vazio.pdf"
    vazio.write_bytes(b"")

    assert "não foi possível ler" in resumir_pdf(vazio).lower()


def test_resumo_existente_e_reaproveitado_sem_chamar_a_ia(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF")
    (tmp_path / "doc.pdf.resumo.md").write_text("resumo ja gerado", encoding="utf-8")

    with patch.object(resumo_documento, "perguntar") as mock_ia:
        assert resumir_pdf(pdf) == "resumo ja gerado"
        mock_ia.assert_not_called()


def test_pdf_sem_texto_extraivel_nao_chama_a_ia(tmp_path):
    pdf = tmp_path / "escaneado.pdf"
    pdf.write_bytes(b"%PDF")

    with patch.object(resumo_documento, "_extrair_texto_pdf", return_value=""), \
         patch.object(resumo_documento, "perguntar") as mock_ia:
        resultado = resumir_pdf(pdf)

    mock_ia.assert_not_called()
    assert "escaneado" in resultado.lower() or "extrair texto" in resultado.lower()


def test_texto_longo_e_truncado_antes_de_ir_para_a_ia(tmp_path):
    pdf = tmp_path / "longo.pdf"
    pdf.write_bytes(b"%PDF")
    texto = "a" * (resumo_documento.MAX_CARACTERES_TEXTO + 5_000)

    with patch.object(resumo_documento, "_extrair_texto_pdf", return_value=texto), \
         patch.object(resumo_documento, "perguntar", return_value="resumo") as mock_ia:
        resumir_pdf(pdf)

    enviado = mock_ia.call_args.args[0]
    assert len(enviado) == resumo_documento.MAX_CARACTERES_TEXTO


def test_jurisprudencia_sem_ementa_nao_chama_a_ia():
    item = ItemJurisprudencia(base="acordao", chave="A-1", sumario=None, titulo=None)

    with patch("pesquisacontratos.ai.resumo_jurisprudencia.perguntar") as mock_ia:
        resultado = resumir(item)

    mock_ia.assert_not_called()
    assert "sem ementa" in resultado.lower()


def test_jurisprudencia_usa_titulo_quando_falta_sumario():
    item = ItemJurisprudencia(base="sumula", chave="S-1", sumario=None,
                               titulo="SÚMULA TCU 255", tipo="SÚMULA")

    with patch("pesquisacontratos.ai.resumo_jurisprudencia.perguntar",
                return_value="explicacao") as mock_ia:
        assert resumir(item) == "explicacao"

    assert "SÚMULA TCU 255" in mock_ia.call_args.args[0]
