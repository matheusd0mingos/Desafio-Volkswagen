"""Minhas pendências: cada pendência vira uma pergunta em português, com a ação certa para ela.
Sem nome de tabela, sem mensagem de constraint, sem 'None'."""
from __future__ import annotations

import re
from datetime import date

import pandas as pd
import streamlit as st

from validacao.adaptadores.sqlite.base_operacional import SqliteBase
from validacao.aplicacao.operacao import AtualizarStatusFrota, LancarLeituraKm, Resposta, SubstituirLeituraKm
from validacao.aplicacao.portas import RecusadoPeloBanco
from validacao.dominio.modelos import Config

ICONE = {"leitura_km": "🛣️", "status_frota": "🚚", "ocorrencia": "⚠️", "teste": "🧪"}
ABA = {"leitura_km": "Quilometragem", "status_frota": "Frota", "ocorrencia": "Ocorrências", "teste": "Plano de testes"}


def dmy(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "—"


def km_br(n) -> str:
    return f"{float(n):,.0f}".replace(",", ".")


def _ok(msg: str) -> None:
    st.session_state["pend_ok"] = msg
    st.rerun()


def _resolveu(r: Resposta, base: SqliteBase | None = None, pid: int | None = None) -> None:
    if r.aceito:
        if base is not None and pid is not None:
            base.resolver_pendencia(pid)
        _ok(r.mensagem)
    (st.warning if r.pede_confirmacao else st.error)(r.mensagem)


def _descartar(base: SqliteBase, pid: int, texto: str = "Não procede: descartar") -> None:
    if st.button(texto, key=f"desc_{pid}", type="tertiary"):
        base.resolver_pendencia(pid)
        _ok("Pendência descartada.")


def _reenviar(base: SqliteBase, pid: int, dados: dict, sucesso: str) -> None:
    try:
        base.reenviar_pendencia(pid, dados)
        _ok(sucesso)
    except RecusadoPeloBanco as e:
        st.error(str(e).split(" (regra do banco")[0])


# ───────── um cartão por tipo de pendência ─────────
def _km(base, cfg, eu, p, d):
    data, veic, pid = date.fromisoformat(d["data"]), p.chave, int(p.id)
    digitado = d.get("km")
    regra = p.motivo
    if regra.startswith("Salto"):
        titulo = f"{km_br(digitado)} km parece ter um zero a mais"
    elif regra.startswith("Km em unidade"):
        titulo = f"{str(digitado).replace('.', ',')} km parece ter sido digitado em mil km"
    elif regra.startswith("Km regrediu"):
        titulo = f"{km_br(digitado)} km é menor que a leitura anterior"
    elif regra.startswith("Km vazio"):
        titulo = "leitura sem km"
    elif regra.startswith("Duas leituras"):
        titulo = "duas leituras no mesmo dia: qual é a certa?"
    elif regra.startswith("Veículo não existe"):
        titulo = "leitura de um veículo que não está na frota"
    else:
        titulo = regra
    st.markdown(f"#### 🛣️ {veic} · {data:%d/%m/%Y}: {titulo}")
    st.caption(f"Regra: {regra}")

    if regra.startswith("Veículo não existe"):
        st.write(f"O {veic} não está no cadastro da logística. Se o veículo existe, peça o cadastro e lance de novo; "
                 "se foi erro de digitação, descarte.")
        _descartar(base, pid)
        return
    if regra.startswith("Duas leituras"):
        _mesmo_dia(base, cfg, eu, p, d, data, veic, pid)
        return
    if regra.startswith("Km vazio"):
        st.write("A linha foi lançada sem o km. Informe o valor do hodômetro naquele dia, ou descarte se não houve leitura.")
    elif regra.startswith("Km regrediu"):
        st.write("O km não pode diminuir. Confira o hodômetro: provavelmente um dígito trocado.")
    tem_sugestao = pd.notna(p.valor_sugerido)
    c1, c2 = st.columns(2) if tem_sugestao else (None, st.columns([1, 1])[0])
    if tem_sugestao:
        with c1, st.container(border=True):
            st.write(f"Sugestão: **{km_br(p.valor_sugerido)} km**")
            if st.button("✅ Usar a sugestão", key=f"sug_{pid}", type="primary"):
                _resolveu(LancarLeituraKm(base, cfg).executar(veic, data, float(p.valor_sugerido), eu, pendencia_id=pid))
    with c2, st.container(border=True):
        val = st.number_input("Km correto", min_value=0.0, step=10.0, format="%.0f", value=None,
                              placeholder="digite o km do hodômetro", key=f"val_{pid}")
        if st.button("Enviar", key=f"env_{pid}", disabled=val is None):
            _resolveu(LancarLeituraKm(base, cfg).executar(veic, data, val, eu, pendencia_id=pid))
    _descartar(base, pid)


def _mesmo_dia(base, cfg, eu, p, d, data, veic, pid):
    na_base = base.leitura_do_dia(veic, data)
    antes = base.leitura_vizinha(veic, data, depois=False)
    depois = base.leitura_vizinha(veic, data, depois=True)
    st.write(f"O Excel tinha **duas leituras do {veic} no mesmo dia**. Uma entrou na base; esta ficou esperando. "
             "Só o dono sabe qual é a do hodômetro.")
    cols = st.columns(4)
    if antes:
        cols[0].metric(f"Antes · {antes.data:%d/%m}", km_br(antes.km))
    if na_base:
        cols[1].metric(f"Na base · {data:%d/%m}", km_br(na_base[0]))
    cols[2].metric(f"Esta pendência · {data:%d/%m}", km_br(d["km"]))
    if depois:
        cols[3].metric(f"Depois · {depois.data:%d/%m}", km_br(depois.km))
    st.caption("As duas cabem entre a leitura anterior e a seguinte, então a regra não consegue decidir sozinha.")
    a, b = st.columns(2)
    if na_base and a.button(f"✅ A da base está certa ({km_br(na_base[0])} km)", key=f"mant_{pid}", type="primary"):
        base.resolver_pendencia(pid)
        _ok(f"Mantida a leitura de {km_br(na_base[0])} km do {veic} em {data:%d/%m/%Y}.")
    if b.button(f"Trocar para esta ({km_br(d['km'])} km)", key=f"troc_{pid}"):
        _resolveu(SubstituirLeituraKm(base, cfg).executar(veic, data, float(d["km"]), eu, pendencia_id=pid))


def _frota(base, cfg, eu, p, d):
    pid = int(p.id)
    st.markdown(f"#### 🚚 {p.chave} está “{d['status']}” desde {dmy(d['data'])}, sem motivo")
    st.write("Veículo fora de operação precisa de **motivo** e, se possível, **previsão de retorno**, "
             "para o Gate saber quando ele volta.")
    c1, c2 = st.columns([2, 1])
    motivo = c1.text_input("Motivo", placeholder="ex.: troca de embreagem", key=f"mot_{pid}")
    prev = c2.date_input("Previsão de retorno (opcional)", None, format="DD/MM/YYYY", key=f"prev_{pid}")
    if st.button("Salvar", key=f"sal_{pid}", type="primary", disabled=not motivo.strip()):
        _resolveu(AtualizarStatusFrota(base).executar(p.chave, date.fromisoformat(d["data"]), d["status"], motivo, prev),
                  base, pid)
    _descartar(base, pid, "O veículo está disponível: descartar")


def _orfao(base, p, d, tabela):
    pid = int(p.id)
    era = d.get("chassi")
    nome = "O teste" if tabela == "teste" else "A ocorrência"
    st.markdown(f"#### {ICONE[tabela]} {nome} {p.chave} aponta para o {era}, que não está na frota")
    st.write(f"Provável erro de digitação no veículo. Escolha o veículo certo, ou descarte se o {era} não existir.")
    v = base.veiculos()
    esc = st.selectbox("Veículo correto", v["codigo"], index=None, placeholder="escolha…", key=f"vei_{pid}")
    if st.button("Corrigir", key=f"cor_{pid}", type="primary", disabled=esc is None):
        chassi = v.loc[v["codigo"] == esc, "chassi"].iloc[0]
        _reenviar(base, pid, dict(d, chassi=chassi), f"{p.chave} corrigido para o {esc}.")
    _descartar(base, pid)


def _status_oc(base, p, d):
    pid = int(p.id)
    st.markdown(f"#### ⚠️ {p.chave}: “{d['descricao']}” está com status “?”")
    st.write("Sem status, a falha não entra na contagem do Gate. Em que pé ela está?")
    c1, c2 = st.columns(2)
    s = c1.radio("Status", ["Aberto", "Em análise", "Fechado"], horizontal=True, index=None, key=f"st_{pid}")
    fech = c2.date_input("Fechada em", None, format="DD/MM/YYYY", key=f"fe_{pid}") if s == "Fechado" else None
    pronto = s is not None and (s != "Fechado" or fech is not None)
    if st.button("Salvar", key=f"sal_{pid}", type="primary", disabled=not pronto):
        _reenviar(base, pid, dict(d, status=s, fechamento=fech.isoformat() if fech else None),
                  f"{p.chave} agora está “{s}”.")
    _descartar(base, pid)


def _datas_oc(base, p, d):
    pid = int(p.id)
    st.markdown(f"#### ⚠️ {p.chave}: fechada em {dmy(d['fechamento'])}, antes de abrir ({dmy(d['abertura'])})")
    st.write("Uma das duas datas está errada. Corrija:")
    c1, c2 = st.columns(2)
    ab = c1.date_input("Aberta em", date.fromisoformat(d["abertura"]), format="DD/MM/YYYY", key=f"ab_{pid}")
    fe = c2.date_input("Fechada em", date.fromisoformat(d["fechamento"]), format="DD/MM/YYYY", key=f"fe_{pid}")
    if fe < ab:
        st.caption("⛔ A data de fechamento ainda está antes da abertura.")
    if st.button("Salvar", key=f"sal_{pid}", type="primary", disabled=fe < ab):
        _reenviar(base, pid, dict(d, abertura=ab.isoformat(), fechamento=fe.isoformat()), f"Datas de {p.chave} corrigidas.")
    _descartar(base, pid)


def _sem_id(base, p, d):
    pid = int(p.id)
    proximo = base.proximo_id_ocorrencia()
    v = base.veiculos()
    veic = v.loc[v["chassi"] == d["chassi"], "codigo"]
    st.markdown(f"#### ⚠️ {veic.iloc[0] if len(veic) else ''} · “{d['descricao']}” veio sem número")
    st.write("A falha já conta no Gate com um número provisório. Dê o número definitivo:")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        if st.button(f"✅ Usar o próximo número ({proximo})", key=f"prox_{pid}", type="primary"):
            _renomear(base, p.chave, proximo, pid)
    with c2, st.container(border=True):
        txt = st.text_input("Ou informe o número que você usava", placeholder="ex.: 117", key=f"id_{pid}")
        num = re.sub(r"\D", "", txt or "")
        if st.button("Usar este número", key=f"usar_{pid}", disabled=not num):
            _renomear(base, p.chave, f"OC-{int(num):04d}", pid)


def _renomear(base, antigo, novo, pid):
    try:
        base.renomear_ocorrencia(antigo, novo, pid)
        _ok(f"Ocorrência agora é {novo}.")
    except RecusadoPeloBanco as e:
        st.error(str(e).split(" (regra do banco")[0])


def _generico(base, p, d):
    pid = int(p.id)
    st.markdown(f"#### {ICONE.get(p.tabela, '•')} {p.chave}: {p.motivo}")
    edit = st.data_editor(pd.DataFrame([d]).astype(object), hide_index=True, key=f"ed_{pid}")
    if st.button("Salvar", key=f"ree_{pid}", type="primary"):
        _reenviar(base, pid, {k: (None if pd.isna(v) or v == "" else v) for k, v in edit.iloc[0].items()},
                  "Linha aceita pela base.")
    _descartar(base, pid)


def cartao(base: SqliteBase, cfg: Config, eu: str, p) -> None:
    d = dict(p.dados)
    with st.container(border=True):
        if p.tabela == "leitura_km":
            _km(base, cfg, eu, p, d)
        elif p.tabela == "status_frota":
            _frota(base, cfg, eu, p, d)
        elif p.motivo == "Ocorrência sem ID":
            _sem_id(base, p, d)
        elif "FOREIGN KEY" in p.motivo and p.tabela in ("teste", "ocorrencia"):
            _orfao(base, p, d, p.tabela)
        elif "status_ocorrencia_lista" in p.motivo:
            _status_oc(base, p, d)
        elif "fechamento_apos_abertura" in p.motivo:
            _datas_oc(base, p, d)
        else:
            _generico(base, p, d)
        st.caption(f"Origem: linha {p.linha_origem} da aba {ABA.get(p.tabela, p.tabela)} do Excel · "
                   f"barrado pelo {'domínio (regra entre linhas)' if p.barrado_por == 'Domínio' else 'banco'}")
