from __future__ import annotations

import csv as csv_module
import json

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from pesquisacontratos import db
from pesquisacontratos.ai.busca_nl import interpretar
from pesquisacontratos.ai.client import IANaoConfiguradaError
from pesquisacontratos.ai.resumo_documento import resumir_pdf
from pesquisacontratos.ai.resumo_jurisprudencia import resumir as resumir_jurisprudencia_ia
from pesquisacontratos.config import ia_configurada
from pesquisacontratos.jurisprudencia import tcu as tcu_conector
from pesquisacontratos.jurisprudencia.tcu import TCUBloqueadoError
from pesquisacontratos.procurement import comprasnet, pncp
from pesquisacontratos.procurement.downloader import baixar_documentos
from pesquisacontratos.procurement.models import Contratacao

console = Console()

CONECTORES_PROCUREMENT = {"pncp": pncp, "comprasnet": comprasnet}


def _celula(valor, padrao: str = "-") -> Text:
    """Célula de tabela a partir de dado externo (API/IA).

    Vai como Text, e não como str: o rich interpretaria `[...]` no texto como
    markup — objetos de licitação ("[LOTE 1]") e ementas do TCU (que vêm com
    HTML) chegam a apagar trechos na exibição, e um `[/algo]` solto derruba o
    comando com MarkupError.
    """
    texto = "" if valor is None else str(valor)
    return Text(texto if texto.strip() else padrao)


@click.group()
def main():
    """Consulta de contratações públicas (PNCP/ComprasNet) e jurisprudência do TCU."""


def _executar_busca(objeto: str, esfera: str | None, ano: int | None, situacao: str | None,
                     tipo: str | None, fontes: str) -> list[Contratacao]:
    conn = db.conectar()
    resultados: list[Contratacao] = []
    for nome_fonte in fontes.split(","):
        nome_fonte = nome_fonte.strip()
        conector = CONECTORES_PROCUREMENT.get(nome_fonte)
        if not conector:
            console.print(f"[yellow]Fonte desconhecida ignorada: {nome_fonte}[/yellow]")
            continue
        try:
            itens = conector.buscar(objeto, esfera=esfera, ano=ano, situacao=situacao,
                                     tipo_contratacao=tipo)
        except Exception as exc:  # nunca deixa uma fonte derrubar as demais
            console.print(f"[red]Erro consultando {nome_fonte}: {escape(str(exc))}[/red]")
            continue
        for item in itens:
            db.upsert_contratacao(conn, item.as_db_dict())
        resultados.extend(itens)
    return resultados


def _tabela_contratacoes(resultados: list[Contratacao]) -> Table:
    tabela = Table(show_lines=False)
    for coluna in ("Fonte", "Órgão", "Esfera/UF", "Objeto", "Modalidade", "Tipo", "Situação",
                   "Nº controle"):
        tabela.add_column(coluna, overflow="fold")
    for r in resultados:
        tabela.add_row(
            _celula(r.fonte), _celula(r.orgao_nome),
            _celula(f"{r.esfera or '-'}/{r.uf or '-'}"),
            _celula((r.objeto or "")[:80]), _celula(r.modalidade),
            _celula(r.tipo_contratacao), _celula(r.situacao), _celula(r.numero_controle),
        )
    return tabela


def _salvar_csv_contratacoes(resultados: list[Contratacao], caminho: str) -> None:
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv_module.writer(f)
        writer.writerow(["fonte", "numero_controle", "orgao_nome", "esfera", "uf", "objeto",
                          "modalidade", "tipo_contratacao", "situacao", "ano", "data_publicacao",
                          "url_portal"])
        for r in resultados:
            writer.writerow([r.fonte, r.numero_controle, r.orgao_nome, r.esfera, r.uf, r.objeto,
                              r.modalidade, r.tipo_contratacao, r.situacao, r.ano,
                              r.data_publicacao, r.url_portal])


@main.command()
@click.option("--objeto", required=True, help="Texto livre do objeto contratado.")
@click.option("--esfera", type=click.Choice(["federal", "estadual", "municipal", "distrital"]))
@click.option("--ano", type=int)
@click.option("--situacao", help='Ex.: "em andamento", "finalizada".')
@click.option("--tipo", "tipo_contratacao", type=click.Choice(["licitacao", "direta"]))
@click.option("--fontes", default="pncp,comprasnet", show_default=True)
@click.option("--salvar", "csv_path", help="Caminho de um .csv para exportar os resultados.")
def buscar(objeto, esfera, ano, situacao, tipo_contratacao, fontes, csv_path):
    """Busca contratações por objeto, esfera, ano, situação e tipo de contratação."""
    resultados = _executar_busca(objeto, esfera, ano, situacao, tipo_contratacao, fontes)
    console.print(_tabela_contratacoes(resultados))
    console.print(f"[bold]{len(resultados)}[/bold] resultado(s).")
    if csv_path:
        _salvar_csv_contratacoes(resultados, csv_path)
        console.print(f"Salvo em {csv_path}")


@main.command("buscar-ia")
@click.argument("texto_livre")
@click.option("--fontes", default="pncp,comprasnet", show_default=True)
@click.option("--salvar", "csv_path", help="Caminho de um .csv para exportar os resultados.")
def buscar_ia(texto_livre, fontes, csv_path):
    """Busca em linguagem natural (usa IA para sugerir objeto/esfera/tipo)."""
    if not ia_configurada():
        console.print("[yellow]IA não configurada — defina NVIDIA_API_KEY no .env. "
                       "Fazendo busca literal com o texto informado.[/yellow]")
    filtros = interpretar(texto_livre)
    console.print(f"[dim]Interpretado como: {escape(str(filtros))}[/dim]")
    resultados = _executar_busca(filtros["objeto"], filtros["esfera"], None, None,
                                  filtros["tipo_contratacao"], fontes)
    console.print(_tabela_contratacoes(resultados))
    console.print(f"[bold]{len(resultados)}[/bold] resultado(s).")
    if csv_path:
        _salvar_csv_contratacoes(resultados, csv_path)
        console.print(f"Salvo em {csv_path}")


@main.command()
@click.option("--id", "numero_controle", required=True, help="numero_controle_pncp da contratação.")
@click.option("--fonte", default="pncp", type=click.Choice(["pncp", "comprasnet"]))
def docs(numero_controle, fonte):
    """Baixa ETP, Termo de Referência e Matriz de Riscos de uma contratação."""
    conn = db.conectar()
    row = conn.execute(
        "SELECT * FROM contratacoes WHERE fonte=? AND numero_controle=?", (fonte, numero_controle)
    ).fetchone()
    if not row:
        console.print("[red]Contratação não encontrada no cache local. Rode `buscar` antes.[/red]")
        return

    contratacao = Contratacao(
        fonte=row["fonte"], numero_controle=row["numero_controle"], objeto=row["objeto"],
        orgao_cnpj=row["orgao_cnpj"], orgao_nome=row["orgao_nome"], esfera=row["esfera"],
        poder=row["poder"], uf=row["uf"], municipio=row["municipio"], modalidade=row["modalidade"],
        tipo_contratacao=row["tipo_contratacao"], situacao=row["situacao"], ano=row["ano"],
        data_publicacao=row["data_publicacao"], url_portal=row["url_portal"],
        json_bruto=json.loads(row["json_bruto"]) if row["json_bruto"] else None,
    )
    conector = CONECTORES_PROCUREMENT[fonte]
    documentos = conector.listar_documentos(contratacao)
    if not documentos:
        console.print("[yellow]Nenhum ETP/Termo de Referência/Matriz de Riscos encontrado para esta contratação.[/yellow]")
        return

    baixados = baixar_documentos(conn, row["id"], contratacao, documentos)
    for caminho in baixados:
        console.print("[green]Baixado:[/green]", _celula(caminho))
    console.print(f"{len(baixados)}/{len(documentos)} documento(s) baixado(s).")


@main.command("resumir-docs")
@click.option("--id", "numero_controle", required=True)
@click.option("--fonte", default="pncp", type=click.Choice(["pncp", "comprasnet"]))
def resumir_docs(numero_controle, fonte):
    """Resume com IA os documentos já baixados de uma contratação (rode `docs` antes)."""
    conn = db.conectar()
    row = conn.execute(
        "SELECT c.id FROM contratacoes c WHERE c.fonte=? AND c.numero_controle=?",
        (fonte, numero_controle),
    ).fetchone()
    if not row:
        console.print("[red]Contratação não encontrada no cache local.[/red]")
        return
    documentos = conn.execute(
        "SELECT * FROM documentos WHERE contratacao_id=? AND caminho_local IS NOT NULL",
        (row["id"],),
    ).fetchall()
    if not documentos:
        console.print("[yellow]Nenhum documento baixado ainda. Rode `docs --id ...` antes.[/yellow]")
        return
    for doc in documentos:
        console.print(f"[bold]{escape(str(doc['tipo_documento']))}[/bold] "
                       f"({escape(str(doc['caminho_local']))})")
        try:
            resumo = resumir_pdf(doc["caminho_local"])
        except IANaoConfiguradaError as exc:
            console.print(f"[yellow]{escape(str(exc))}[/yellow]")
            return
        console.print(_celula(resumo))
        console.print()


@main.command()
@click.option("--termo", required=True)
@click.option("--base", type=click.Choice(list(tcu_conector.BASES.keys())))
@click.option("--ano", type=int)
@click.option("--relator")
@click.option("--colegiado")
@click.option("--resumir-ia", is_flag=True, default=False)
@click.option("--salvar", "csv_path", help="Caminho de um .csv para exportar os resultados.")
def jurisprudencia(termo, base, ano, relator, colegiado, resumir_ia, csv_path):
    """Busca acórdãos, súmulas, jurisprudência selecionada e publicações do TCU."""
    conn = db.conectar()
    try:
        resultados = tcu_conector.buscar(termo, base=base, ano=ano, relator=relator,
                                          colegiado=colegiado)
    except TCUBloqueadoError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        console.print("[dim]Tentando busca local (resultados já pesquisados anteriormente)...[/dim]")
        linhas = db.buscar_jurisprudencia_local(conn, termo)
        if not linhas:
            console.print("[yellow]Nada encontrado no cache local.[/yellow]")
            return
        _imprimir_jurisprudencia_local(linhas, csv_path)
        return

    ids_por_item = {}
    for item in resultados:
        item_id = db.upsert_jurisprudencia(conn, item.as_db_dict())
        ids_por_item[item.chave] = item_id

    tabela = Table(show_lines=False)
    for coluna in ("Base", "Tipo", "Número/Ano", "Colegiado", "Relator", "Data", "Resumo oficial"):
        tabela.add_column(coluna, overflow="fold")
    if resumir_ia:
        tabela.add_column("Resumo IA", overflow="fold")

    for item in resultados:
        resumo_ia_texto = ""
        if resumir_ia:
            try:
                resumo_ia_texto = resumir_jurisprudencia_ia(item)
                db.salvar_resumo_ia_jurisprudencia(conn, ids_por_item[item.chave], resumo_ia_texto)
            except IANaoConfiguradaError as exc:
                resumo_ia_texto = f"[IA não configurada: {exc}]"

        linha = [_celula(item.base), _celula(item.tipo),
                 _celula(f"{item.numero or '-'}/{item.ano or '-'}"),
                 _celula(item.colegiado), _celula(item.relator), _celula(item.data_sessao),
                 _celula((item.sumario or "")[:150])]
        if resumir_ia:
            linha.append(_celula(resumo_ia_texto))
        tabela.add_row(*linha)

    console.print(tabela)
    console.print(f"[bold]{len(resultados)}[/bold] resultado(s).")

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv_module.writer(f)
            writer.writerow(["base", "chave", "tipo", "numero", "ano", "colegiado", "relator",
                              "data_sessao", "sumario", "url_pdf", "url_pesquisa_integrada"])
            for item in resultados:
                writer.writerow([item.base, item.chave, item.tipo, item.numero, item.ano,
                                  item.colegiado, item.relator, item.data_sessao, item.sumario,
                                  item.url_pdf, item.url_pesquisa_integrada])
        console.print(f"Salvo em {csv_path}")


def _imprimir_jurisprudencia_local(linhas, csv_path) -> None:
    tabela = Table(show_lines=False)
    for coluna in ("Base", "Tipo", "Número/Ano", "Colegiado", "Relator", "Sumário"):
        tabela.add_column(coluna, overflow="fold")
    for linha in linhas:
        tabela.add_row(_celula(linha["base"]), _celula(linha["tipo"]),
                        _celula(f"{linha['numero'] or '-'}/{linha['ano'] or '-'}"),
                        _celula(linha["colegiado"]), _celula(linha["relator"]),
                        _celula((linha["sumario"] or "")[:150]))
    console.print(tabela)
    console.print(f"[bold]{len(linhas)}[/bold] resultado(s) do cache local.")
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv_module.writer(f)
            writer.writerow(["base", "chave", "tipo", "numero", "ano", "colegiado", "relator",
                              "sumario"])
            for linha in linhas:
                writer.writerow([linha["base"], linha["chave"], linha["tipo"], linha["numero"],
                                  linha["ano"], linha["colegiado"], linha["relator"],
                                  linha["sumario"]])
        console.print(f"Salvo em {csv_path}")


@main.command()
def status():
    """Testa conectividade de cada fonte de dados e mostra se a IA está configurada."""
    tabela = Table(show_lines=False)
    tabela.add_column("Fonte")
    tabela.add_column("Status")
    tabela.add_column("Detalhe", overflow="fold")

    for nome, conector in CONECTORES_PROCUREMENT.items():
        ok, msg = conector.testar_conexao()
        tabela.add_row(nome, "[green]OK[/green]" if ok else "[red]FALHOU[/red]", _celula(msg))

    ok, msg = tcu_conector.testar_conexao()
    tabela.add_row("tcu (jurisprudência)", "[green]OK[/green]" if ok else "[red]FALHOU[/red]",
                    _celula(msg))

    if ia_configurada():
        tabela.add_row("IA (Nvidia NIM)", "[green]OK[/green]", "NVIDIA_API_KEY configurada")
    else:
        tabela.add_row("IA (Nvidia NIM)", "[yellow]DESATIVADA[/yellow]",
                        "NVIDIA_API_KEY não definida no .env")

    console.print(tabela)


if __name__ == "__main__":
    main()
