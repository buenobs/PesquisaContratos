from unittest.mock import MagicMock, patch

from pesquisacontratos.procurement import comprasnet

# Estrutura de exemplo (campos conforme o endpoint
# 1_consultarContratacoes_PNCP_14133, ver docstring do conector) usada como
# fixture nos testes, sem depender de rede.
ITEM_EXEMPLO = {
    "numeroControlePNCP": "00394460005887-1-000019/2025",
    "objetoCompra": "Aquisição de material de escritório para uso administrativo",
    "orgaoEntidadeCnpj": "00394460005887",
    "orgaoEntidadeRazaoSocial": "MINISTERIO DA ECONOMIA",
    "orgaoEntidadeEsferaId": "F",
    "orgaoEntidadePoderId": "E",
    "unidadeOrgaoUfSigla": "DF",
    "unidadeOrgaoMunicipioNome": "Brasília",
    "modalidadeNome": "Pregão Eletrônico",
    "tipoInstrumentoConvocatorioNome": "Edital",
    "anoCompraPncp": 2025,
    "sequencialCompraPncp": 19,
    "dataPublicacaoPncp": "2025-04-22T17:50:39",
    "dataEncerramentoPropostaPncp": "2099-01-01T00:00:00",
    "contratacaoExcluida": False,
    "situacaoCompraNomePncp": "Divulgada no PNCP",
}


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


@patch("pesquisacontratos.procurement.comprasnet.requests.get")
def test_buscar_filtra_objeto_no_cliente(mock_get):
    # tipo_contratacao="licitacao" percorre as duas modalidades de licitação
    # (MODALIDADES_LICITACAO); só a primeira chamada devolve itens.
    outro_item = {**ITEM_EXEMPLO, "objetoCompra": "Serviço de limpeza predial"}
    mock_get.side_effect = [
        _mock_response({"resultado": [ITEM_EXEMPLO, outro_item]}),
        _mock_response({"resultado": []}),
    ]

    resultados = comprasnet.buscar("material de escritório", ano=2025, tipo_contratacao="licitacao")

    assert len(resultados) == 1
    assert resultados[0].numero_controle == "00394460005887-1-000019/2025"
    assert resultados[0].tipo_contratacao == "licitacao"
    assert resultados[0].situacao == "em andamento"


@patch("pesquisacontratos.procurement.comprasnet.requests.get")
def test_buscar_filtra_por_esfera(mock_get):
    mock_get.return_value = _mock_response({"resultado": [ITEM_EXEMPLO]})

    resultados = comprasnet.buscar("material", esfera="municipal", tipo_contratacao="licitacao")

    assert resultados == []


@patch("pesquisacontratos.procurement.comprasnet.requests.get")
def test_buscar_ignora_contratacao_excluida(mock_get):
    item_excluido = {**ITEM_EXEMPLO, "contratacaoExcluida": True}
    mock_get.side_effect = [
        _mock_response({"resultado": [item_excluido]}),
        _mock_response({"resultado": []}),
    ]

    resultados = comprasnet.buscar("material", tipo_contratacao="licitacao")

    assert len(resultados) == 1
    assert resultados[0].situacao == "cancelada"


def test_situacao_calculada_aceita_data_com_timezone():
    # dataEncerramentoPropostaPncp com timezone não deve levantar TypeError
    # ao comparar com dt.datetime.now() (naive).
    item = {**ITEM_EXEMPLO, "dataEncerramentoPropostaPncp": "2099-01-01T00:00:00+00:00"}

    assert comprasnet._situacao_calculada(item) == "em andamento"


@patch("pesquisacontratos.procurement.comprasnet.pncp.listar_documentos")
def test_listar_documentos_reaproveita_pncp(mock_listar_pncp):
    mock_listar_pncp.return_value = ["doc-fake"]
    contratacao = comprasnet._to_contratacao(ITEM_EXEMPLO)

    documentos = comprasnet.listar_documentos(contratacao)

    mock_listar_pncp.assert_called_once_with(contratacao)
    assert documentos == ["doc-fake"]
