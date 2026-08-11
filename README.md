# PesquisaContratos

Ferramenta de linha de comando para:

1. **Buscar contratações públicas** (PNCP + ComprasNet) por objeto, esfera de
   governo, ano, situação e tipo de contratação (licitação ou aquisição
   direta), com download de **ETP**, **Termo de Referência** e **Matriz de
   Gerenciamento de Riscos**.
2. **Buscar jurisprudência do TCU** (acórdãos, súmulas, jurisprudência
   selecionada, publicações, respostas a consultas) — módulo independente do
   item 1.
3. Opcionalmente, usar **IA (Nvidia NIM, gratuita)** para: interpretar buscas
   em linguagem natural, resumir os documentos baixados e explicar
   acórdãos/súmulas em linguagem simples.

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -e ".[dev]"
copy .env.example .env      # depois edite o .env (veja "IA" abaixo)
```

## Comandos

```bash
# Buscar contratações
python -m pesquisacontratos buscar --objeto "material de escritório" \
    --esfera municipal --ano 2025 --situacao "em andamento" --tipo licitacao

# Baixar ETP/Termo de Referência/Matriz de Riscos de um resultado
python -m pesquisacontratos docs --id <numero_controle_pncp>

# Buscar em linguagem natural (requer IA configurada)
python -m pesquisacontratos buscar-ia "preciso comprar computadores para uma escola municipal"

# Resumir com IA os documentos já baixados
python -m pesquisacontratos resumir-docs --id <numero_controle_pncp>

# Buscar jurisprudência do TCU
python -m pesquisacontratos jurisprudencia --termo "parcelamento do objeto" --base acordao
python -m pesquisacontratos jurisprudencia --termo "exclusividade" --base sumula --resumir-ia

# Diagnóstico de conectividade
python -m pesquisacontratos status
```

Todo resultado de busca fica salvo em cache local (`pesquisacontratos.db`,
SQLite, ignorado pelo git). Documentos baixados vão para `downloads/` (também
ignorado pelo git).

## IA (Nvidia NIM)

1. Crie uma conta gratuita em https://build.nvidia.com e gere uma API key.
2. Copie `.env.example` para `.env` e preencha `NVIDIA_API_KEY`.
3. Confira em build.nvidia.com/explore qual o nome exato do modelo que você
   quer usar e ajuste `NVIDIA_MODEL` se necessário (o padrão sugerido é
   `meta/llama-3.1-8b-instruct`).

Sem a chave, o sistema funciona normalmente — só os comandos/flags de IA
(`buscar-ia`, `resumir-docs`, `jurisprudencia --resumir-ia`) ficam
desativados, com um aviso claro em vez de erro.

## Escopo e limitações por fonte

| Fonte | O que é usado | Limitações conhecidas |
|---|---|---|
| **PNCP** | `/api/search` (busca) + `/api/pncp/v1/orgaos/.../arquivos` (documentos) | Parâmetros de filtro server-side (esfera, status) não são oficialmente documentados nem sempre respeitados pela API — o sistema filtra no cliente por segurança. "Situação" (em andamento/finalizada) é derivada da data de fim de vigência da proposta, pois o PNCP não expõe esse status diretamente. |
| **ComprasNet / Compras.gov.br** | `/modulo-contratacoes/1_consultarContratacoes_PNCP_14133` (dadosabertos.compras.gov.br) | **Não existe busca por texto livre nesta API** — o filtro por objeto é feito no cliente sobre os resultados de uma janela de datas. Cobre só o Poder Executivo Federal. `codigoModalidade` usa uma tabela de códigos própria do Compras.gov.br (diferente da do PNCP); os códigos usados (3, 5, 6, 7) foram confirmados por amostragem real, outros podem existir mas não foram mapeados. |
| **TCU (jurisprudência)** | `pesquisa.apps.tcu.gov.br/rest/publico/base/{base}/documentosResumidos` | Endpoint público, mas protegido por um firewall de aplicação sensível a rajadas de requisições — o conector já espaça as chamadas e faz backoff, mas buscas muito seguidas ainda podem ser bloqueadas temporariamente (nesse caso, o comando cai automaticamente para uma busca no cache local, se houver dados de buscas anteriores). Os nomes de campo de cada base foram confirmados para `sumula`; para `jurisprudencia_selecionada`, `publicacao` e `resposta_consulta` foram assumidos por analogia e podem precisar de ajuste. |
| **IA (Nvidia NIM)** | `integrate.api.nvidia.com/v1` (compatível com OpenAI) | Depende de chave gratuita gerada pelo usuário; catálogo de modelos gratuitos muda com frequência. |

### Fora do escopo (avaliados e excluídos)

- **CGU / Portal da Transparência**, **BLL Compras**, **BNC Compras**, **BB
  Licitações-e**: excluídos por instrução explícita do usuário.
- **CONNECTJUS**: não é um portal de compras (é uma plataforma colaborativa
  do CNJ) — não se aplica a este sistema.

## Testes

```bash
pytest
```

Os testes usam respostas reais das APIs capturadas como fixtures (mock),
sem depender de rede.

## Estrutura

```
pesquisacontratos/
├── cli.py                 comandos: buscar, buscar-ia, docs, resumir-docs, jurisprudencia, status
├── db.py                  schema SQLite (contratações + jurisprudência, com índice FTS5)
├── procurement/           conectores PNCP e ComprasNet
├── jurisprudencia/        conector TCU
└── ai/                    cliente Nvidia NIM e os três usos de IA
```
