"""Impacto no Gate Review: o antes x depois da preparação e o pacote do Gate gerado pela base."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from validacao.adaptadores.sqlite.base_operacional import MENSAGENS, SqliteBase

LARGO = "stretch"


def br(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


# ───────── página conceitual: como muda a preparação ─────────
def impacto(versoes_falhas: tuple[int, int, int], pct_problema: float, km_em_dia: int, frota: int) -> None:
    st.header("2.1 Como muda a preparação do Gate Review")
    st.caption("A segunda pergunta do gestor: o que a fonte única muda no jeito de preparar o Gate.")
    m = st.columns(4)
    for c, (rot, novo, hoje) in zip(m, [
            ("Preparação", "≤ 4 h", "hoje: 2 pessoas × 3 dias"),
            ("Consolidação manual", "0 fontes", "hoje: 5 fontes copiadas à mão"),
            ("Versões do mesmo número", "1", f"hoje: {versoes_falhas[0]} ({versoes_falhas[1]} a {versoes_falhas[2]} falhas)"),
            ("Km em dia na reunião", "≥ 95%", f"hoje: {km_em_dia} de {frota} veículos")]):
        c.metric(rot, novo)
        c.caption(hoje)

    st.subheader("Etapa por etapa")
    st.dataframe(pd.DataFrame([
        ("Coleta", "Pedido de planilhas por e-mail a cada engenheiro e à logística",
         "Deixa de existir: o dado está na base desde o lançamento"),
        ("Consolidação", "Duas pessoas copiam e conciliam 5 fontes, cerca de 3 dias",
         "Consulta automática por programa"),
        ("Conferência", "O número diverge do controle do engenheiro",
         "Divergência vira pendência com responsável antes da reunião"),
        ("Material", "Slides montados do zero a cada Gate", "Pacote do Gate gerado pela plataforma"),
        ("Reunião", "Discussão sobre qual número está correto", "Discussão de riscos e decisão de avanço"),
        ("Depois da reunião", "Correções refeitas nos slides", "Correção feita na origem, refletida no painel"),
    ], columns=["Etapa", "Hoje", "Com a base única"]), hide_index=True, width=LARGO)

    st.subheader("A semana do Gate")
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.markdown("**Hoje**")
        st.markdown("- **D-5:** pedir os dados a cada responsável\n"
                    "- **D-4 a D-2:** consolidar 5 fontes e montar slides\n"
                    "- **D-1:** conferir números com os engenheiros\n"
                    "- **D0:** reunião começa discutindo divergências")
    with b, st.container(border=True):
        st.markdown("**Com a base única**")
        st.markdown("- **Contínuo:** cada engenheiro lança e resolve as próprias pendências\n"
                    "- **D-2:** gestor confere o critério de prontidão e cobra só o que falta\n"
                    "- **D-1:** pacote do Gate gerado pela plataforma\n"
                    "- **D0:** reunião discute riscos e decide o avanço")

    st.subheader("Critério de prontidão para o Gate")
    st.write("O programa só vai ao Gate com o dado pronto. A plataforma verifica três condições:")
    st.markdown("1. Nenhuma pendência de qualidade em aberto nos veículos do programa\n"
                "2. Todos os veículos com leitura de km na última semana\n"
                "3. Todas as ocorrências com status definido")
    st.caption(f"Linha de base desta base: {pct_problema:.0%} das linhas com algum problema e {km_em_dia} de {frota} "
               "veículos com km em dia na data de corte.")
    st.button("Ver o pacote do Gate gerado →", on_click=lambda: st.session_state.update(pagina="▶ Pacote do Gate"))


# ───────── página operacional: o pacote do Gate ─────────
def _pendencias_por_programa(base: SqliteBase, programa: str) -> pd.DataFrame:
    v = base.veiculos()
    prog_cod = dict(zip(v["codigo"], v["programa"]))
    prog_chassi = dict(zip(v["chassi"], v["programa"]))
    p = base.pendencias()

    def prog(r) -> str | None:
        if r.chave in prog_cod:
            return prog_cod[r.chave]
        return prog_chassi.get((r.dados or {}).get("chassi"))
    p["programa"] = [prog(r) for r in p.itertuples()]
    return p[p["programa"] == programa]


def pacote(base: SqliteBase, dias: int) -> None:
    st.header("▶ Pacote do Gate: gerado pela base, não montado à mão")
    ref = base.data_referencia()
    gate = base.gate()
    programa = st.segmented_control("Programa", gate["programa"].tolist(), default=gate["programa"].iloc[0])
    if not programa:
        return
    g = gate[gate["programa"] == programa].iloc[0]
    km = base.km_em_dia(dias)
    km = km[km["programa"] == programa]
    oc = base.ocorrencias()
    v = base.veiculos()
    oc = oc[oc["veiculo"].isin(v[v["programa"] == programa]["codigo"])]
    te = base.testes_pendentes()
    te = te[te["veiculo"].isin(v[v["programa"] == programa]["codigo"])]
    fr = base.status_frota_atual()
    fr = fr[fr["programa"] == programa]
    pend = _pendencias_por_programa(base, programa)
    pend["motivo"] = pend["motivo"].map(_amigavel)
    fr["status"] = fr["status"].replace({"Sem status": "Sem status válido (ver pendência)"})

    criterios = [
        ("Pendências de qualidade resolvidas", len(pend) == 0, f"{len(pend)} em aberto"),
        (f"Km de todos os veículos em até {dias} dias", bool(km["em_dia"].all()),
         f"{int(km['em_dia'].sum())} de {len(km)} em dia"),
        ("Ocorrências com status definido", True, "garantido pelo banco"),
    ]
    pronto = all(ok for _, ok, _ in criterios)
    (st.success if pronto else st.warning)(
        f"**Programa {programa} {'pronto' if pronto else 'ainda não está pronto'} para o Gate** · "
        f"referência {ref:%d/%m/%Y}")
    for nome, ok, det in criterios:
        st.markdown(f"{'✅' if ok else '⚠️'} **{nome}** · {det}")

    m = st.columns(4)
    m[0].metric("Km rodado", br(g["km_rodado"]))
    m[1].metric("Falhas abertas", int(g["falhas_abertas"]))
    m[2].metric("Testes atrasados", int(g["testes_atrasados"]))
    m[3].metric("Veículos disponíveis", f"{int((fr['status'] == 'Disponível').sum())} / {len(fr)}")

    a, b = st.columns(2)
    with a:
        st.markdown("**Falhas abertas**")
        st.dataframe(_limpo(oc, OC), hide_index=True, width=LARGO)
        st.markdown("**Testes não concluídos**")
        st.dataframe(_limpo(te, TE), hide_index=True, width=LARGO)
    with b:
        st.markdown("**Frota**")
        st.dataframe(_limpo(fr, FR), hide_index=True, width=LARGO)
        st.markdown("**Pendências que impedem o Gate**")
        if pend.empty:
            st.caption("Nenhuma.")
        else:
            st.dataframe(_limpo(pend, PE), hide_index=True, width=LARGO)

    md = _markdown(programa, ref, g, fr, oc, te, pend, criterios, pronto)
    st.download_button("⬇️ Baixar o pacote do Gate (.md)", md.encode("utf-8"),
                       f"Pacote_Gate_{programa}_{ref:%Y%m%d}.md", type="primary")


def _amigavel(motivo: str) -> str:
    return next((v for k, v in MENSAGENS.items() if k in motivo), motivo)


def _limpo(df: pd.DataFrame, nomes: dict) -> pd.DataFrame:
    return df[list(nomes)].rename(columns=nomes).astype(object).where(lambda x: x.notna(), "—")


OC = {"ocorrencia_id": "Ocorrência", "veiculo": "Veículo", "descricao": "Descrição", "status": "Status", "abertura": "Aberta em"}
TE = {"teste_id": "Teste", "veiculo": "Veículo", "tipo": "Tipo", "prevista": "Prevista", "status": "Status"}
FR = {"veiculo": "Veículo", "status": "Status", "motivo": "Motivo", "previsao_retorno": "Previsão de retorno"}
PE = {"chave": "Item", "responsavel": "Responsável", "motivo": "Motivo"}


def _tabela(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Nenhum._\n"
    cols = list(df.columns)
    linhas = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    linhas += ["| " + " | ".join("" if pd.isna(x) else str(x) for x in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(linhas) + "\n"


def _markdown(programa, ref: date, g, fr, oc, te, pend, criterios, pronto) -> str:
    crit = "\n".join(f"- {'OK' if ok else 'PENDENTE'}: {n} ({d})" for n, ok, d in criterios)
    return (f"# Pacote do Gate Review: programa {programa}\n\n"
            f"Referência: {ref:%d/%m/%Y} · gerado automaticamente a partir da base única\n\n"
            f"## Prontidão: {'pronto' if pronto else 'não pronto'}\n\n{crit}\n\n"
            f"## Números do programa\n\n"
            f"- Km rodado: {br(g['km_rodado'])}\n- Falhas abertas: {int(g['falhas_abertas'])}\n"
            f"- Testes concluídos: {int(g['testes_concluidos'])}\n- Testes atrasados: {int(g['testes_atrasados'])}\n\n"
            f"## Frota\n\n{_tabela(_limpo(fr, FR))}\n"
            f"## Falhas abertas\n\n{_tabela(_limpo(oc, OC))}\n"
            f"## Testes não concluídos\n\n{_tabela(_limpo(te, TE))}\n"
            f"## Pendências de qualidade\n\n{_tabela(_limpo(pend, PE))}")
