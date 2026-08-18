from unittest.mock import MagicMock, patch

import pytest

from pesquisacontratos.jurisprudencia import tcu

# Amostra real (capturada em https://pesquisa.apps.tcu.gov.br/rest/publico/base/sumula/documentosResumidos)
SUMULA_EXEMPLO = {
    "KEY": "SUMULA-EJURIS-18838",
    "TIPO": "SÚMULA",
    "TITULO": "SÚMULA TCU 255: ",
    "ANOAPROVACAO": "2010",
    "NUMERO": "255",
    "VIGENTE": "true",
    "AUTORTESE": "JOSÉ JORGE",
    "ENUNCIADO": "<p>SÚMULA TCU 255: Nas contratações em que o objeto só possa ser fornecido "
                 "por produtor, empresa ou representante comercial exclusivo...</p>",
    "COLEGIADO": "Plenário",
    "DTATUALIZACAO": "20170512",
}


def _mock_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_buscar_base_especifica(mock_get):
    mock_get.return_value = _mock_response({
        "quantidadeEncontrada": 1, "inicio": 0, "documentos": [SUMULA_EXEMPLO],
    })

    resultados = tcu.buscar("diligencia", base="sumula")

    assert len(resultados) == 1
    item = resultados[0]
    assert item.base == "sumula"
    assert item.chave == "SUMULA-EJURIS-18838"
    assert item.numero == "255"
    assert item.colegiado == "Plenário"
    assert "SÚMULA TCU 255" in item.sumario


@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_buscar_filtra_por_ano(mock_get):
    mock_get.return_value = _mock_response({
        "quantidadeEncontrada": 1, "inicio": 0, "documentos": [SUMULA_EXEMPLO],
    })

    resultados = tcu.buscar("diligencia", base="sumula", ano=1999)

    assert resultados == []


@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
def test_bloqueio_waf_gera_erro_tratavel(mock_sleep, mock_get):
    resp_bloqueada = MagicMock()
    resp_bloqueada.status_code = 200
    resp_bloqueada.json.side_effect = ValueError("not json")
    mock_get.return_value = resp_bloqueada

    # Nenhuma base respondeu: buscar() propaga um erro tratável, que é o que
    # faz a CLI cair para o cache local (ver test_regressoes.py).
    with pytest.raises(tcu.TCUBloqueadoError):
        tcu.buscar("qualquer coisa", base="sumula")
