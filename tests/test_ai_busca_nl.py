from unittest.mock import patch

from pesquisacontratos.ai.busca_nl import interpretar


@patch("pesquisacontratos.ai.busca_nl.perguntar")
def test_interpretar_json_valido(mock_perguntar):
    mock_perguntar.return_value = (
        '{"objeto": "computadores", "esfera": "municipal", "tipo_contratacao": "licitacao"}'
    )

    resultado = interpretar("preciso comprar computadores para uma escola municipal")

    assert resultado == {"objeto": "computadores", "esfera": "municipal",
                          "tipo_contratacao": "licitacao"}


@patch("pesquisacontratos.ai.busca_nl.perguntar")
def test_interpretar_valor_invalido_vira_none(mock_perguntar):
    mock_perguntar.return_value = '{"objeto": "computadores", "esfera": "Pública", "tipo_contratacao": null}'

    resultado = interpretar("computadores para escola")

    assert resultado["esfera"] is None
    assert resultado["tipo_contratacao"] is None


@patch("pesquisacontratos.ai.busca_nl.perguntar", side_effect=RuntimeError("IA indisponível"))
def test_interpretar_cai_para_fallback_em_erro(mock_perguntar):
    resultado = interpretar("compra de veiculos")

    assert resultado == {"objeto": "compra de veiculos", "esfera": None, "tipo_contratacao": None}
