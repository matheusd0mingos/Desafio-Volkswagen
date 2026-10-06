"""Páginas da plataforma: o fluxo desejado funcionando (carga inicial do Excel, depois só a plataforma)."""
from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd
import streamlit as st

from validacao.adaptadores.sqlite.base_operacional import SqliteBase
from validacao.aplicacao.operacao import (AbrirOcorrencia, AtualizarStatusFrota, FecharOcorrencia,
                                          LancarLeituraKm, RegistrarTesteRealizado, Resposta)
from validacao.aplicacao.portas import RecusadoPeloBanco
from validacao.dominio.modelos import Config

LARGO = "stretch"
CAMPOS_EXTRAS = {"status_frota": ["motivo", "previsao_retorno"]}


# ───────── utilidades de interface ─────────
def usuario(base: SqliteBase) -> str:
    opcoes = base.pessoas() + ["Logística"]
    if st.session_state.get("usuario_w") not in opcoes:          # (re)inicia ao voltar para a página
        salvo = st.session_state.get("usuario_salvo")
        st.session_state["usuario_w"] = salvo if salvo in opcoes else opcoes[0]
    u = st.selectbox("👤 Você é (no protótipo; em produção, login corporativo)", opcoes, key="usuario_w")
    st.session_state["usuario_salvo"] = u
    return u


def registrar(chave: str, r: Resposta, acao: Callable[[bool], Resposta] | None = None) -> None:
    st.session_state[f"msg_{chave}"] = r
    if r.pede_confirmacao and acao:
        st.session_state[f"conf_{chave}"] = acao
    else:
        st.session_state.pop(f"conf_{chave}", None)


def mostrar(chave: str) -> None:
    r: Resposta | None = st.session_state.get(f"msg_{chave}")
    if r:
        (st.success if r.aceito else st.warning if r.pede_confirmacao else st.error)(r.mensagem)
    conf = st.session_state.get(f"conf_{chave}")
    if conf and st.button("Confirmar mesmo assim", key=f"btn_{chave}"):
        st.session_state.pop(f"conf_{chave}")
        r2 = conf(True)
        if r2.aceito and chave.startswith("pend_"):
            st.session_state["pend_ok"] = r2.mensagem
        registrar(chave, r2)
        st.rerun()


# ───────── páginas ─────────
def lancar(base: SqliteBase, cfg: Config) -> None:
    st.header("▶ Lançar dados: uma vez, já validado")
    st.caption("O Excel serviu só para a carga inicial. Daqui em diante, cada engenheiro atualiza por aqui.")
    eu = usuario(base)
    veic = base.veiculos()["codigo"].tolist()
    ref = base.data_referencia()
    t_km, t_oc, t_fr, t_te = st.tabs(["🛣️ Quilometragem", "⚠️ Ocorrência", "🚚 Status da frota", "✅ Teste realizado"])

    with t_km:
        with st.form("f_km", clear_on_submit=False):
            c1, c2, c3 = st.columns(3)
            v = c1.selectbox("Veículo", veic)
            d = c2.date_input("Data", ref, format="DD/MM/YYYY")
            km = c3.number_input("Km acumulado", min_value=0.0, step=10.0, format="%.0f")
            if st.form_submit_button("Registrar leitura", type="primary"):
                caso = LancarLeituraKm(base, cfg)
                acao = lambda conf, v=v, d=d, km=km: caso.executar(v, d, km, eu, confirmado=conf)
                registrar("km", acao(False), acao)
        mostrar("km")

    with t_oc:
        a, b = st.columns(2)
        with a, st.form("f_oc"):
            st.subheader("Abrir")
            v = st.selectbox("Veículo", veic, key="oc_v")
            desc = st.text_input("Descrição", placeholder="ex.: Falha CAN intermitente")
            d = st.date_input("Abertura", ref, format="DD/MM/YYYY", key="oc_d")
            if st.form_submit_button("Abrir ocorrência", type="primary"):
                caso = AbrirOcorrencia(base, cfg)
                acao = lambda conf, v=v, desc=desc, d=d: caso.executar(v, desc, d, eu, confirmado=conf)
                registrar("oc", acao(False), acao)
        with b, st.form("f_fecha"):
            st.subheader("Fechar")
            ab = base.ocorrencias()
            ops = [f"{r.ocorrencia_id} · {r.veiculo} · {r.descricao}" for r in ab.itertuples()]
            esc = st.selectbox("Ocorrência aberta", ops)
            d = st.date_input("Fechamento", ref, format="DD/MM/YYYY", key="fe_d")
            if st.form_submit_button("Fechar ocorrência") and esc:
                registrar("oc", FecharOcorrencia(base).executar(esc.split(" · ")[0], d))
        mostrar("oc")

    with t_fr:
        with st.form("f_fr"):
            c1, c2, c3 = st.columns(3)
            v = c1.selectbox("Veículo", veic, key="fr_v")
            d = c2.date_input("Desde", ref, format="DD/MM/YYYY", key="fr_d")
            s = c3.selectbox("Status", ["Disponível", "Em manutenção", "Indisponível"])
            c4, c5 = st.columns([2, 1])
            motivo = c4.text_input("Motivo (obrigatório se não estiver disponível)")
            prev = c5.date_input("Previsão de retorno", None, format="DD/MM/YYYY")
            if st.form_submit_button("Atualizar status", type="primary"):
                registrar("fr", AtualizarStatusFrota(base).executar(v, d, s, motivo, prev))
        mostrar("fr")

    with t_te:
        tp = base.testes_pendentes()
        with st.form("f_te"):
            ops = [f"{r.teste_id} · {r.veiculo} · {r.tipo} · {r.status}" for r in tp.itertuples()]
            esc = st.selectbox("Teste", ops)
            d = st.date_input("Realizado em", ref, format="DD/MM/YYYY", key="te_d")
            if st.form_submit_button("Registrar conclusão", type="primary") and esc:
                registrar("te", RegistrarTesteRealizado(base).executar(esc.split(" · ")[0], d))
        mostrar("te")

    st.subheader("Últimos lançamentos pela plataforma")
    ul = base.ultimos_lancamentos()
    if ul.empty:
        st.caption("Nenhum ainda: tudo na base veio da carga inicial.")
    else:
        st.dataframe(ul, hide_index=True, width=LARGO)


def pendencias(base: SqliteBase, cfg: Config) -> None:
    from validacao.adaptadores.web.pendencias_ui import cartao
    st.header("▶ Minhas pendências: o que só o dono pode resolver")
    st.caption("O que a carga inicial não conseguiu aceitar sozinha. Nada foi apagado: cada item espera a sua decisão.")
    eu = usuario(base)
    ok = st.session_state.pop("pend_ok", None)
    if ok:
        st.success(ok)
    p = base.pendencias(eu)
    if p.empty:
        st.success("Nada pendente. 🎉")
        return
    tipos = p["tabela"].map({"leitura_km": "quilometragem", "status_frota": "status da frota",
                             "ocorrencia": "ocorrência", "teste": "teste"}).value_counts()
    st.markdown(f"**{len(p)} {'pendência' if len(p) == 1 else 'pendências'}:** "
                + ", ".join(f"{n} de {t}" for t, n in tipos.items()))
    for r in p.itertuples():
        cartao(base, cfg, eu, r)


def gate_ao_vivo(base: SqliteBase, dias: int, reiniciar: Callable[[], None]) -> None:
    st.header("▶ Gate ao vivo: lendo a base única, não o Excel")
    ref = st.date_input("Data de referência do Gate", base.data_referencia(), format="DD/MM/YYYY")
    if ref != base.data_referencia():
        base.definir_data_referencia(ref)
    g, kd, pend = base.gate(), base.km_em_dia(dias), base.pendencias()
    m = st.columns(4)
    m[0].metric("Falhas abertas (confirmadas)", int(g["falhas_abertas"].sum()))
    m[1].metric("Km rodado", f"{g['km_rodado'].sum():,.0f}".replace(",", "."))
    m[2].metric("Pendências com os donos", len(pend))
    m[3].metric(f"Km em dia (≤ {dias} dias)", f"{int(kd['em_dia'].sum())} / {len(kd)}")
    st.dataframe(g, hide_index=True, width=LARGO)
    a, b = st.columns(2)
    a.bar_chart(g, x="programa", y="falhas_abertas")
    b.bar_chart(g, x="programa", y=["testes_concluidos", "testes_atrasados"], stack=False)
    with st.expander("Quilometragem por veículo"):
        st.dataframe(kd, hide_index=True, width=LARGO)
    with st.expander("Pendências por responsável"):
        st.dataframe(pend.groupby("responsavel").size().rename("pendências").reset_index(), hide_index=True)
    st.divider()
    ok = st.checkbox("Quero apagar os lançamentos e refazer a carga inicial a partir do Excel")
    if st.button("↺ Reiniciar base", disabled=not ok):
        reiniciar()
        st.rerun()
