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


def _pagina(docs, total=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"documentos": docs,
                               "quantidadeEncontrada": total if total is not None else len(docs)}
    return resp


@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_pagina_quando_filtro_esvazia_a_primeira_pagina(mock_get, _sleep):
    """Filtros são client-side: uma página cheia pode ser toda descartada."""
    descartados = [{"KEY": f"S-{i}", "ANOAPROVACAO": "2010"} for i in range(tcu.TAM_PAGINA)]
    alvo = [{"KEY": "S-alvo", "ANOAPROVACAO": "2024"}]
    mock_get.side_effect = [_pagina(descartados, total=25), _pagina(alvo, total=25)]

    resultados = tcu.buscar("x", base="sumula", ano=2024)

    assert [r.chave for r in resultados] == ["S-alvo"]
    assert mock_get.call_count == 2
    # a 2ª chamada precisa avançar o offset, senão repetiria a mesma página
    assert mock_get.call_args_list[1].kwargs["params"]["inicio"] == tcu.TAM_PAGINA


@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_para_ao_atingir_a_quantidade_pedida(mock_get, _sleep):
    docs = [{"KEY": f"S-{i}"} for i in range(tcu.TAM_PAGINA)]
    mock_get.return_value = _pagina(docs, total=1000)

    resultados = tcu.buscar("x", base="sumula", quantidade=5)

    assert len(resultados) == 5
    assert mock_get.call_count == 1


@patch("pesquisacontratos.jurisprudencia.tcu.time.sleep", return_value=None)
@patch("pesquisacontratos.jurisprudencia.tcu.requests.get")
def test_respeita_teto_de_paginas_para_nao_provocar_o_firewall(mock_get, _sleep):
    docs = [{"KEY": f"S-{i}", "ANOAPROVACAO": "2010"} for i in range(tcu.TAM_PAGINA)]
    mock_get.return_value = _pagina(docs, total=10_000)

    # nada passa no filtro de ano, então só o teto interrompe o laço
    tcu.buscar("x", base="sumula", ano=2024, max_paginas=3)

    assert mock_get.call_count == 3
