"""Base de dados: o banco visto por dentro, lido ao vivo (diagrama, tabelas e consulta SQL só leitura)."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from validacao.adaptadores.sqlite.base_operacional import SqliteBase
from validacao.aplicacao.portas import RecusadoPeloBanco

LARGO = "stretch"
NUCLEO = ["programa", "veiculo", "status_frota", "leitura_km", "teste", "ocorrencia"]
APOIO = ["pendencia", "log_qualidade", "parametro"]

EXEMPLOS = {
    "Gate por programa (view)": "SELECT * FROM vw_gate_programa",
    "Falhas abertas por veículo": """SELECT v.codigo AS veiculo, v.programa_id AS programa, COUNT(*) AS falhas_abertas
FROM ocorrencia o JOIN veiculo v USING (chassi)
WHERE o.status <> 'Fechado'
GROUP BY v.codigo ORDER BY falhas_abertas DESC""",
    "Km rodado por veículo": """SELECT v.codigo AS veiculo, MIN(l.km) AS primeira, MAX(l.km) AS ultima,
       MAX(l.km) - MIN(l.km) AS km_rodado, MAX(l.data) AS ultima_leitura
FROM leitura_km l JOIN veiculo v USING (chassi)
GROUP BY v.codigo ORDER BY km_rodado DESC""",
    "Pendências por responsável": """SELECT responsavel, barrado_por, COUNT(*) AS pendencias
FROM pendencia WHERE resolvida = 0
GROUP BY responsavel, barrado_por ORDER BY pendencias DESC""",
    "O que entrou pela plataforma": """SELECT 'km' AS tipo, chassi, data, km AS valor, responsavel, lancado_em
FROM leitura_km WHERE origem = 'plataforma'
UNION ALL
SELECT 'ocorrência', chassi, abertura, descricao, responsavel, lancado_em
FROM ocorrencia WHERE origem = 'plataforma' ORDER BY lancado_em DESC""",
}


def _no(obj: dict, cor: str, fonte: str) -> str:
    fk_cols = {f["coluna"] for f in obj["fks"]}
    linhas = []
    for c in obj["colunas"]:
        marca = ("PK " if c["pk"] else "") + ("FK " if c["nome"] in fk_cols else "")
        peso = ("<B>", "</B>") if c["pk"] else ("", "")
        tipo = f' <FONT COLOR="#8a8f98">{html.escape(c["tipo"])}</FONT>' if c["tipo"] else ""
        linhas.append(f'<TR><TD ALIGN="LEFT" PORT="{c["nome"]}">{peso[0]}{marca}{html.escape(c["nome"])}{peso[1]}'
                      f'{tipo}</TD></TR>')
    titulo = f'{obj["nome"]} · {obj["linhas"]} linha{"s" if obj["linhas"] != 1 else ""}'
    return (f'"{obj["nome"]}" [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">'
            f'<TR><TD BGCOLOR="{cor}"><FONT COLOR="{fonte}"><B>{html.escape(titulo)}</B></FONT></TD></TR>'
            + "".join(linhas) + "</TABLE>>];")


def diagrama(estr: list[dict], incluir_apoio: bool) -> str:
    por_nome = {o["nome"]: o for o in estr}
    nos, arestas = [], []
    for nome in NUCLEO:
        if nome in por_nome:
            nos.append(_no(por_nome[nome], "#16202b" if nome == "veiculo" else "#b45a12", "white"))
    if incluir_apoio:
        nos += [_no(por_nome[n], "#d9d6cf", "#1b2430") for n in APOIO if n in por_nome]
        nos += [_no(o, "#e8eef7", "#1f5fa8") for o in estr if o["tipo"] == "view"]
    visiveis = set(NUCLEO) | (set(APOIO) | {o["nome"] for o in estr if o["tipo"] == "view"} if incluir_apoio else set())
    for o in estr:
        if o["nome"] not in visiveis:
            continue
        for f in o["fks"]:
            if f["tabela"] in visiveis:
                ref = f["ref"] or f["coluna"]
                arestas.append(f'"{o["nome"]}":"{f["coluna"]}" -> "{f["tabela"]}":"{ref}" [label=" N:1"];')
    return ("digraph { rankdir=LR; bgcolor=\"transparent\"; node [shape=plaintext, fontname=\"Helvetica\", fontsize=10];"
            " edge [color=\"#b45a12\", fontname=\"Helvetica\", fontsize=9, fontcolor=\"#b45a12\", arrowhead=normal];\n"
            + "\n".join(nos) + "\n" + "\n".join(arestas) + "\n}")


def pagina(base: SqliteBase) -> None:
    st.header("▶ Base de dados: o banco visto por dentro")
    st.caption("Lido ao vivo do SQLite. Cada lançamento na plataforma muda estes números.")
    estr = base.estrutura()
    tabelas = [o for o in estr if o["tipo"] == "table"]

    m = st.columns(4)
    m[0].metric("Tabelas", len(tabelas))
    m[1].metric("Views", sum(o["tipo"] == "view" for o in estr))
    m[2].metric("Linhas no núcleo", sum(o["linhas"] for o in tabelas if o["nome"] in NUCLEO))
    m[3].metric("Chaves estrangeiras", sum(len(o["fks"]) for o in tabelas))

    t_diag, t_dados, t_sql = st.tabs(["🗺️ Diagrama", "📋 Tabelas", "🔎 Consulta SQL"])
    with t_diag:
        apoio = st.toggle("Mostrar tabelas de apoio e views", value=False)
        st.graphviz_chart(diagrama(estr, apoio), width=LARGO)
        st.caption("PK = chave primária · FK = chave estrangeira · seta = N para 1. "
                   "Em escuro, o veículo: o centro do modelo.")
        a, b = st.columns(2)
        with a:
            st.markdown("**Linhas por tabela**")
            st.bar_chart(pd.DataFrame([(o["nome"], o["linhas"]) for o in tabelas if o["nome"] in NUCLEO + APOIO],
                                      columns=["tabela", "linhas"]), x="tabela", y="linhas", horizontal=True)
        with b:
            st.markdown("**De onde veio cada dado**")
            orig = base.origem_dos_dados()
            st.bar_chart(orig, x="tabela", y="linhas", color="origem", horizontal=True)
            st.caption("‘carga inicial’ veio do Excel, uma vez; ‘plataforma’ foi lançado depois.")

    with t_dados:
        nomes = [o["nome"] for o in estr]
        esc = st.selectbox("Tabela ou view", nomes, index=nomes.index("veiculo") if "veiculo" in nomes else 0)
        obj = next(o for o in estr if o["nome"] == esc)
        a, b = st.columns([1, 2])
        with a:
            st.markdown(f"**Estrutura de `{esc}`**")
            fk = {f["coluna"]: f'{f["tabela"]}.{f["ref"] or f["coluna"]}' for f in obj["fks"]}
            st.dataframe(pd.DataFrame([{"Coluna": c["nome"], "Tipo": c["tipo"] or "—",
                                        "Chave": " + ".join((["PK"] if c["pk"] else []) +
                                                            ([f"FK → {fk[c['nome']]}"] if c["nome"] in fk else [])),
                                        "Obrigatória": "sim" if c["obrigatorio"] or c["pk"] else ""}
                                       for c in obj["colunas"]]), hide_index=True, width=LARGO)
        with b:
            st.markdown(f"**Conteúdo** · {obj['linhas']} linhas")
            st.dataframe(base.consultar(f'SELECT * FROM "{esc}"'), hide_index=True, width=LARGO)

    with t_sql:
        st.caption("Consulta livre, só leitura: a conexão é aberta em modo read-only, então nenhuma escrita passa.")
        ex = st.selectbox("Exemplo", list(EXEMPLOS))
        sql = st.text_area("SQL", EXEMPLOS[ex], height=150, key=f"sqlro_{ex}")
        if st.button("Executar consulta", type="primary"):
            try:
                df = base.consultar(sql)
                st.dataframe(df, hide_index=True, width=LARGO)
                st.caption(f"{len(df)} linha(s).")
            except RecusadoPeloBanco as e:
                st.error(str(e))
