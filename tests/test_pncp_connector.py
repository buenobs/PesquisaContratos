from unittest.mock import MagicMock, patch

from pesquisacontratos.procurement import pncp

# Amostra real (capturada em https://pncp.gov.br/api/search/) usada como fixture
# para não depender de rede nos testes automatizados.
ITEM_EXEMPLO = {
    "id": "343f4ddeda381af132061dbe6a6c566b",
    "title": "Edital nº 0100100/0002/2025",
    "description": "Alienação de mercadorias apreendidas pela Receita Federal",
    "item_url": "/compras/00394460005887/2025/19",
    "ano": "2025",
    "numero_sequencial": "19",
    "numero_controle_pncp": "00394460005887-1-000019/2025",
    "orgao_cnpj": "00394460005887",
    "orgao_nome": "MINISTERIO DA ECONOMIA",
    "esfera_id": "F",
    "esfera_nome": "Federal",
    "poder_id": "E",
    "poder_nome": "Executivo",
    "uf": "DF",
    "municipio_nome": "Brasília",
    "modalidade_licitacao_nome": "Leilão - Eletrônico",
    "situacao_nome": "Divulgada no PNCP",
    "data_publicacao_pncp": "2025-04-22T17:50:39.737436688",
    "data_fim_vigencia": None,
    "cancelado": False,
    "tipo_id": "1",
    "tipo_nome": "Edital",
}

ITEM_DIRETA_2024 = {**ITEM_EXEMPLO, "ano": "2024", "tipo_id": "2",
                    "tipo_nome": "Aviso de Contratação Direta"}


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_buscar_filtra_por_ano_e_tipo(mock_get):
    mock_get.return_value = _mock_response({"items": [ITEM_EXEMPLO, ITEM_DIRETA_2024], "total": 2})

    resultados = pncp.buscar("mercadorias", ano=2025, tipo_contratacao="licitacao")

    assert len(resultados) == 1
    assert resultados[0].numero_controle == "00394460005887-1-000019/2025"
    assert resultados[0].tipo_contratacao == "licitacao"
    assert resultados[0].esfera == "Federal"


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_buscar_filtra_por_esfera(mock_get):
    mock_get.return_value = _mock_response({"items": [ITEM_EXEMPLO], "total": 1})

    resultados = pncp.buscar("mercadorias", esfera="municipal")

    assert resultados == []


@patch("pesquisacontratos.procurement.pncp.requests.get")
def test_listar_documentos_filtra_tipos_de_interesse(mock_get):
    contratacao = pncp._to_contratacao(ITEM_EXEMPLO)
    mock_get.return_value = _mock_response([
        {"tipoDocumentoId": 1, "url": "https://exemplo/edital.pdf"},
        {"tipoDocumentoId": 7, "url": "https://exemplo/etp.pdf"},
        {"tipoDocumentoId": 4, "url": "https://exemplo/tr.pdf"},
        {"tipoDocumentoId": 9, "url": "https://exemplo/matriz-riscos.pdf"},
    ])

    documentos = pncp.listar_documentos(contratacao)

    tipos = {d.tipo_documento for d in documentos}
    assert tipos == {"ETP", "Termo de Referência", "Matriz de Riscos"}
