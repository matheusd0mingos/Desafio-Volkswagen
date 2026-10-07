"""1.4 Tratamento em Python, passo a passo: o que o código fez, com os casos reais desta base."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from validacao.dominio.servicos import Similaridade

LARGO = "stretch"

# passo → (nome, onde no código, prefixos de regra do log)
PASSOS = [
    ("① Ler", "adaptadores/excel.py · ExcelFonte.ler()", ()),
    ("② Padronizar", "dominio/normalizadores.py",
     ("ID fora do padrão", "Data como texto", "Data em formato americano", "Status com grafia",
      "Status fora da lista", "Nome fora do padrão", "Nome de teste fora", "Ocorrência sem ID", "ID duplicado")),
    ("③ Conferir cada linha", "dominio/regras.py",
     ("Veículo não existe", "Fechamento antes", "Fechada sem data", "Veículo indisponível",
      "Concluído sem data", "Status digitado diverge", "Programa diverge")),
    ("④ Comparar leituras", "dominio/servicos.py · ValidadorLeituras",
     ("Duas leituras", "Km em unidade", "Km regrediu", "Salto de", "Km vazio", "Sem leitura válida")),
    ("⑤ Agrupar duplicatas", "dominio/servicos.py · AnalisadorOcorrencias", ("Provável duplicata", "Mesma falha")),
    ("⑥ Calcular", "status do teste, km rodado, falhas únicas", ()),
    ("⑦ Gravar", "adaptadores/sqlite/repositorio.py", ()),
]
AUTOMATICO = ("ID fora do padrão", "Data como texto", "Data em formato americano", "Status com grafia",
              "Nome fora do padrão", "Nome de teste fora")


def _do_passo(ach: pd.DataFrame, prefixos: tuple) -> pd.DataFrame:
    if not prefixos:
        return ach.iloc[0:0]
    return ach[ach["Regra"].str.startswith(prefixos)]


def _exemplos(df: pd.DataFrame) -> None:
    st.dataframe(df[["Aba", "Linha", "Valor original", "Regra", "Ação"]], hide_index=True, width=LARGO)


def pagina(D: dict, res, cfg) -> None:
    ach, bruto, trat = D["achados"], D["bruto"], D["tratado"]
    st.header("1.4 Tratamento em Python: passo a passo")
    a, b, c = st.columns(3)
    a.info("**1 · Padroniza sozinho** o que é seguro: formato de ID, data, status, nome")
    b.warning("**2 · Pergunta ao dono** o que muda o sentido: km suspeito, duplicata, status “?”")
    c.success("**3 · Nunca apaga:** todo achado guarda a aba e a linha de origem")

    cont = [len(_do_passo(ach, p[2])) for p in PASSOS]
    cols = st.columns(7)
    rotulos = [f"{sum(len(df) for df in bruto.values())} linhas", f"{cont[1]} achados", f"{cont[2]} achados",
               f"{cont[3]} achados", f"{cont[4]} achados", f"{res.falhas_abertas_depois} falhas",
               f"{len(D['banco']['pendencias'])} pendências"]
    for col, (nome, _, _), rot in zip(cols, PASSOS, rotulos):
        with col, st.container(border=True):
            st.markdown(f"**{nome}**")
            st.caption(rot)

    abas = st.tabs([p[0] for p in PASSOS])

    with abas[0]:
        st.markdown("Lê as 4 abas e entrega **linhas Python puras** ao domínio: célula vazia vira `None`, data do "
                    "Excel vira `datetime`. É o único ponto do código que conhece pandas.")
        st.dataframe(pd.DataFrame([(k, len(v), len(v.columns)) for k, v in bruto.items()],
                                  columns=["Aba", "Linhas", "Colunas"]), hide_index=True)
        st.caption(f"Código: {PASSOS[0][1]}")

    with abas[1]:
        st.dataframe(pd.DataFrame([
            ("ID do veículo", "Pega o número com regex e formata PT-NN", "PT 07, pt07, Protótipo 7 → PT-07"),
            ("Data", "Texto aaaa-mm-dd é ISO; em xx/yy/aaaa, se yy > 12 só pode ser americano",
             "09/03/2026 → 2026-03-09 · 03/18/2026 → 2026-03-18"),
            ("Status", "Tira acento, põe em minúscula e procura no catálogo", "ABERTO → Aberto · Concluído → Fechado · ? → Indefinido"),
            ("Pessoa", "Compara sobrenome e inicial com os nomes completos", "marcos s., M. Silva → Marcos Silva"),
            ("Tipo de teste", "Catálogo de variantes", "Durabilidade - pista → Durabilidade em pista"),
            ("ID da ocorrência", "OC-NNNN; vazio vira provisório; repetido ganha -B", "OC-117 → OC-0117 · vazio → OC-SEMID-15"),
        ], columns=["O quê", "Como", "Antes → depois"]), hide_index=True, width=LARGO)
        df = _do_passo(ach, PASSOS[1][2])
        auto = df["Regra"].str.startswith(AUTOMATICO).sum()
        st.caption(f"{auto} corrigidos sozinhos · {len(df) - auto} corrigidos e enviados ao dono (status “?”, ID vazio ou repetido)")
        with st.expander(f"Ver os {len(df)} casos reais"):
            _exemplos(df)

    with abas[2]:
        st.markdown("Uma regra = uma classe pequena. Cada uma olha **uma linha só**.")
        df = _do_passo(ach, PASSOS[2][2])
        st.dataframe(df.groupby("Categoria").size().rename("Casos").reset_index(), hide_index=True)
        with st.expander(f"Ver os {len(df)} casos reais"):
            _exemplos(df)

    with abas[3]:
        _comparar(ach, trat, cfg)

    with abas[4]:
        _agrupar(ach, trat)

    with abas[5]:
        _funil(trat, res)

    with abas[6]:
        bd = D["banco"]
        pend = bd["pendencias"]
        m = st.columns(3)
        m[0].metric("Linhas aceitas pelo banco", int(bd["contagens"]["aceitas"].sum()))
        m[1].metric("Quarentena do domínio", int((pend["barrado_por"] == "Domínio").sum()))
        m[2].metric("Recusadas pelo banco", int((pend["barrado_por"] == "Banco").sum()))
        st.markdown("Grava o **Excel tratado** e a **base SQLite**. O que não entra vira **pendência com o nome do "
                    "dono**, que resolve pela plataforma. Nada é descartado em silêncio.")
        st.caption(f"Código: {PASSOS[6][1]}")


def _comparar(ach, trat, cfg) -> None:
    st.markdown("1. Ordena as leituras **por veículo e por data**.  \n"
                "2. Compara cada leitura com a **última leitura boa** do veículo, não com a anterior qualquer.  \n"
                "3. Aplica 4 regras **nesta ordem**; a primeira que disparar põe a leitura em quarentena.")
    st.dataframe(pd.DataFrame([
        (1, "Mesma data", "data igual à da última boa"),
        (2, "Unidade errada", "km atual ÷ anterior < 0,01 → sugere × 1.000"),
        (3, "Km regrediu", "km atual < anterior"),
        (4, "Salto", f"aumento > {cfg.max_km_semana:,} × semanas".replace(",", ".") + "; se a razão > 5, sugere ÷ 10"),
    ], columns=["Ordem", "Regra", "Conta"]), hide_index=True, width=LARGO)

    km = trat["Leitura_Km"].copy()
    alvo = ["PT-07", "PT-04", "PT-05", "PT-02", "PT-08"]
    v = st.segmented_control("Acompanhe um veículo", [x for x in alvo if x in set(km["Veiculo_ID"])], default="PT-07")
    if not v:
        return
    serie = km[km["Veiculo_ID"] == v].sort_values(["Data", "Linha_origem"])
    regra = {int(r.Linha): r.Regra for r in ach[(ach["Aba"] == "Quilometragem") & (ach["Linha"] != "-")].itertuples()
             if r.Severidade == "Alta" and not r.Regra.startswith("Data em formato")}
    ultima_boa, linhas = None, []
    for r in serie.itertuples():
        compara = "—" if ultima_boa is None else f"{ultima_boa:,.0f}".replace(",", ".")
        if r.Qualidade == "OK":
            resultado = "✅ aceita"
            ultima_boa = r.Km_acumulado
        else:
            resultado = "🚧 " + regra.get(int(r.Linha_origem), "quarentena")
        km_txt = "vazio" if pd.isna(r.Km_acumulado) else f"{r.Km_acumulado:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")
        linhas.append((r.Data.strftime("%d/%m") if pd.notna(r.Data) else "—", km_txt, compara, resultado))
    st.dataframe(pd.DataFrame(linhas, columns=["Data", "Km digitado", "Compara com (última boa)", "Resultado"]),
                 hide_index=True, width=LARGO)
    if v == "PT-07":
        st.caption("Por que a última **boa**: se 21.900 fosse comparado com 18.120 (a leitura errada), todo o resto do "
                   "PT-07 viraria suspeito por causa de um único erro. Comparado com 18.450, são 1.725 km/semana: normal.")
    atras = ach[ach["Regra"].str.startswith("Sem leitura")]
    st.caption(f"Depois, {len(atras)} veículos entram no log por estarem sem leitura boa há mais de "
               f"{cfg.dias_sem_leitura} dias na data de corte.")


def _agrupar(ach, trat) -> None:
    st.markdown("Compara as **palavras** das descrições (sem acento e sem “no”, “de”, “da”…): "
                "**palavras em comum ÷ palavras no total** (similaridade de Jaccard).  \n"
                "≥ 0,5 no **mesmo** veículo = duplicata · ≥ 0,6 em veículos **diferentes** = possível falha sistêmica.")
    oc = trat["Ocorrencia"].set_index("Ocorrencia_ID")
    sim = Similaridade()
    linhas = []
    for r in ach[ach["Regra"].str.startswith(("Provável duplicata", "Mesma falha"))].to_dict("records"):
        outro = r["Regra"].split(" de ")[1].split(" ")[0]
        desc_a = oc.loc[outro, "Descrição"] if outro in oc.index else "?"
        desc_b = r["Valor original"]
        pa, pb = sim.palavras(desc_a), sim.palavras(desc_b)
        tipo = "possível falha sistêmica" if r["Regra"].startswith("Mesma falha") else "duplicata"
        linhas.append((f"{outro} · {desc_a}", desc_b,
                       f"{len(pa & pb)} ÷ {len(pa | pb)} = {len(pa & pb) / len(pa | pb):.2f}".replace(".", ","), tipo))
    st.dataframe(pd.DataFrame(linhas, columns=["Ocorrência", "Comparada com", "Em comum ÷ total", "Resultado"]),
                 hide_index=True, width=LARGO)
    st.caption("A duplicata não é apagada: ganha o mesmo grupo, e o dono confirma.")


def _funil(trat, res) -> None:
    oc = trat["Ocorrencia"]
    veic = set(trat["Veiculo"]["Veiculo_ID"])
    abertas = oc[oc["Status"] != "Fechado"]
    fechados = set(oc.loc[oc["Status"] == "Fechado", "Grupo_duplicata"])
    p1 = abertas[~abertas["Grupo_duplicata"].isin(fechados)]
    p2 = p1[p1["Veiculo_ID"].isin(veic)]
    final = p2["Grupo_duplicata"].nunique()
    dup = p2[p2.duplicated("Grupo_duplicata")]["Ocorrencia_ID"].tolist()
    st.markdown("**O funil das falhas abertas**")
    st.dataframe(pd.DataFrame([
        ("Tudo que não está fechado (planilha crua)", len(abertas), ""),
        ("− grupo já fechado por uma duplicata", len(p1),
         ", ".join(sorted(set(abertas["Ocorrencia_ID"]) - set(p1["Ocorrencia_ID"])))),
        ("− veículo fora da Frota", len(p2), ", ".join(sorted(set(p1["Ocorrencia_ID"]) - set(p2["Ocorrencia_ID"])))),
        ("− duplicatas do mesmo grupo (conta uma vez)", final, ", ".join(dup)),
    ], columns=["Passo", "Falhas", "Saíram"]), hide_index=True, width=LARGO)
    st.caption(f"Resultado: {final} falhas abertas, sendo 2 com status “?” em quarentena. "
               f"Contagens ingênuas da mesma lista: {', '.join(str(v) for v in res.falhas_abertas_antes.values())}.")
    st.markdown("**Também calculado, nunca digitado:** status do teste (data realizada → Concluído; prevista antes do "
                "corte → Atrasado) e km rodado (última − primeira leitura boa de cada veículo).")
