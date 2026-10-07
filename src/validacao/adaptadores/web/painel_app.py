"""Apresentação do case no Streamlit: uma página por pergunta (1.1 a 2.5), com dados ao vivo."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import sqlite3

import pandas as pd
import streamlit as st

from validacao.adaptadores.sqlite.repositorio import conectar, schema_sql
from validacao.adaptadores.sqlite.base_operacional import SqliteBase
from validacao.adaptadores.sqlite.bootstrap import garantir_base
from validacao.adaptadores.web import banco_ui, gate_ui, plataforma, tratamento_ui
from validacao.adaptadores.web.dados import tratar
from validacao.dominio.modelos import Config, LeituraKm, Origem
from validacao.dominio.normalizadores import DataNormalizador, VeiculoIDNormalizador
from validacao.dominio.regras import REGRAS_LEITURA_PADRAO

st.set_page_config(page_title="Case Validation & AI", page_icon="🚚", layout="wide")

PAGINAS = ["👤 About me", "👤 Why this role", "Início", "1.1 Diagnóstico", "1.2 Modelo de dados", "1.3 Padrões e regras", "1.4 Tratamento", "1.4 Carga na base",
           "2.1 Fluxo do Gate", "2.1 Impacto no Gate Review", "▶ Lançar dados", "▶ Minhas pendências", "▶ Gate ao vivo", "▶ Pacote do Gate", "▶ Base de dados", "2.2 Plano de 90 dias", "2.3 Indicadores", "2.4 Adesão",
           "2.5 Inteligência artificial", "Premissas e riscos"]
LARGO = "stretch"


def br(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


# ───────────────────────── barra lateral ─────────────────────────
st.sidebar.title("🚚 Case Validation & AI")
ROTEIROS = {
    "Case · 10 min": ["Início", "1.1 Diagnóstico", "1.2 Modelo de dados", "1.4 Tratamento", "2.1 Impacto no Gate Review",
                      "▶ Lançar dados", "▶ Pacote do Gate", "2.2 Plano de 90 dias", "2.3 Indicadores", "2.4 Adesão",
                      "Premissas e riscos"],
    "Case · 5 min": ["Início", "1.1 Diagnóstico", "1.2 Modelo de dados", "2.1 Impacto no Gate Review",
                     "▶ Lançar dados", "2.2 Plano de 90 dias", "Premissas e riscos"],
    "Apresentação pessoal": ["👤 About me", "👤 Why this role"],
    "Tudo (arguição)": PAGINAS,
}
roteiro = st.sidebar.selectbox("🎬 Roteiro", list(ROTEIROS), index=3, key="roteiro")
VISIVEIS = list(ROTEIROS[roteiro])
st.session_state.setdefault("pagina", VISIVEIS[0])
if st.session_state.get("_roteiro_anterior") != roteiro:            # trocou de roteiro: vai para o início dele
    st.session_state["_roteiro_anterior"] = roteiro
    if st.session_state["pagina"] not in VISIVEIS:
        st.session_state["pagina"] = VISIVEIS[0]
OPCOES = VISIVEIS + ([st.session_state["pagina"]] if st.session_state["pagina"] not in VISIVEIS else [])
st.sidebar.radio("Páginas", OPCOES, key="pagina", label_visibility="collapsed")
if roteiro != "Tudo (arguição)":
    pos = VISIVEIS.index(st.session_state["pagina"]) + 1 if st.session_state["pagina"] in VISIVEIS else 0
    st.sidebar.progress(pos / len(VISIVEIS), text=f"{pos} de {len(VISIVEIS)}")

NOTAS_ON = st.sidebar.toggle("🗣️ Notas do apresentador", help="Desligue antes de compartilhar a tela, ou abra numa 2ª janela só para você.")
with st.sidebar.expander("⚙️ Premissas (mude ao vivo)"):
    max_km = st.slider("Limite de km por semana", 1000, 6000, Config.max_km_semana, 500,
                       help="Acima disso, a leitura é suspeita e vai para o dono confirmar. "
                            "O maior ritmo real na base é ≈ 1.700 km/semana (PT-07).")
    dias = st.slider("Dias sem leitura de km", 3, 21, Config.dias_sem_leitura,
                     help="O km deve ser lançado toda semana. Passou disso, o veículo conta como 'atrasado'.")
arquivo = st.sidebar.file_uploader("Outro Excel do case", type="xlsx")
padrao = Path(os.environ.get("CASE_XLSX", "dados/entrada/Case_Dados_Validacao_.xlsx"))
if arquivo:
    conteudo = arquivo.getvalue()
elif padrao.is_file():
    conteudo = padrao.read_bytes()
else:
    st.info("Envie o Excel do case na barra lateral.")
    st.stop()

D = tratar(conteudo, max_km, dias)
CFG = Config(max_km_semana=max_km, dias_sem_leitura=dias)
BASE_DB = Path(os.environ.get("BASE_DB", "dados/base/validacao.db"))
garantir_base(BASE_DB, conteudo, config=CFG)          # Excel entra só na primeira vez
BASE = SqliteBase(BASE_DB)
res, ach, gate = D["resumo"], D["achados"], D["gate"]
pct = D["com_problema"] / D["total_linhas"]


def navegar(delta: int) -> None:
    seq = VISIVEIS if st.session_state["pagina"] in VISIVEIS else PAGINAS
    i = seq.index(st.session_state["pagina"])
    st.session_state["pagina"] = seq[max(0, min(len(seq) - 1, i + delta))]


def rodape() -> None:
    st.divider()
    a, _, b = st.columns([1, 6, 1])
    a.button("← Anterior", on_click=navegar, args=(-1,), width=LARGO)
    b.button("Próximo →", on_click=navegar, args=(1,), width=LARGO)


def cartao(titulo: str, texto: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{titulo}**")
        st.write(texto)


# ───────────────────────── apresentação pessoal (inglês, 2 páginas, 3 min) ─────────────────────────
ASSETS = Path(__file__).parent / "assets"


def etapa(quando: str, titulo: str, texto: str, atual: bool = False) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([1, 4])
        c1.markdown(f"**:orange[{quando}]**")
        c2.markdown(f"**{titulo}**" + ("  :blue-badge[now]" if atual else ""))
        c2.caption(texto)


def sobre_mim():
    st.caption("PERSONAL PRESENTATION · 1 / 2")
    st.title("Matheus Domingos")
    st.markdown("##### Electrical engineer from IME who builds software for engineering work · Resende, RJ")
    st.write("")
    a, b = st.columns([3, 2], gap="large")
    with a:
        etapa("2019–2023", "B.Sc. Electrical Engineering · IME",
              "Robotics team (Python navigation for a humanoid robot) and research on chaotic dynamical systems")
        etapa("2021–2022", "Data Science Intern · Árvore",
              "Churn and lead-scoring models in Python, Power BI dashboards, SQL")
        etapa("2024–2026", "Electrical Engineer · Army, Belém",
              "Electrical and BIM projects; Python analysis of energy consumption for the free-market migration")
        etapa("2026–now", "Electrical Engineer · Army, Resende",
              "Inspection of a medium-voltage network upgrade: technical reviews, measurements, change orders", atual=True)
    with b:
        with st.container(border=True):
            st.markdown("**Dominica** · founder and developer, since 2025")
            st.caption("Planning and contract intelligence for engineering works: schedules, measurements, "
                       "costs, change orders")
            st.markdown(":gray-badge[C#/.NET] :gray-badge[React] :gray-badge[PostgreSQL] :gray-badge[Docker] "
                        ":gray-badge[Hexagonal architecture] :gray-badge[Automated tests]")
        with st.container(border=True):
            st.markdown("**Education and languages**")
            st.caption("MBA in Software Engineering · PUC Minas (2026)")
            st.caption("English and French: full professional (FCE B2, DELF B2) · Portuguese: native")


def prova(requisito: str, numero: str, rotulo: str, texto: str) -> None:
    with st.container(border=True):
        st.caption(requisito.upper())
        st.metric(rotulo, numero)
        st.write(texto)


def por_que_vaga():
    st.caption("PERSONAL PRESENTATION · 2 / 2")
    st.title("Why this role")
    st.markdown("##### What the role asks for, and where I have already done it")
    st.write("")
    a, b = st.columns([3, 2], gap="large")
    with a:
        x, y = st.columns(2)
        with x:
            prova("Data that drives decisions", "17 sites", "moved to the free energy market",
                  "Python analysis of consumption profiles for Army units across 3 states. "
                  "Team project: first bills 18–30% lower.")
        with y:
            prova("Automate repetitive work", "Apps Script", "and Node.js, replacing spreadsheets",
                  "Automations for technical procurement; scripts that pull labour hours out of SINAPI budgets.")
        x, y = st.columns(2)
        with x:
            prova("Digital tools and dashboards", "Dominica", "built end to end, solo",
                  ".NET and React platform for schedules, measurements and contracts. Power BI as an intern.")
        with y:
            prova("AI and analytics", "ML + tests", "models, then validation",
                  "Churn and lead-scoring models at Árvore. Today I use AI daily and validate it with tests, "
                  "as in this case.")
    with b:
        mapa = ASSETS / "mapa_amazonia_oriental.png"
        if mapa.is_file():
            st.image(str(mapa), caption="Army sites in the Eastern Amazon (Pará, Amapá, Maranhão): "
                                        "scope of the free-market migration", width="stretch")
    st.info("**I have been the engineer on the receiving end of messy spreadsheets. "
            "I want to be the one who turns validation data into faster engineering decisions.**")


# ───────────────────────── páginas ─────────────────────────
def inicio():
    st.caption("CASE TÉCNICO · ENGENHARIA DE DIGITALIZAÇÃO, IA E DADOS DE VALIDAÇÃO")
    st.title("Um número só no Gate Review")
    st.subheader("Quantas falhas estão abertas?")
    cols = st.columns(4)
    for c, (rot, v) in zip(cols, res.falhas_abertas_antes.items()):
        c.metric(rot, v)
    cols[3].metric("Após tratamento (únicas e válidas)", res.falhas_abertas_depois)
    st.markdown("**Mesma lista, quatro respostas.** É essa a discussão que trava o Gate.")
    st.subheader("Quanto a frota rodou?")
    a, b, c = st.columns(3)
    a.metric("Somando a planilha como está", f"{br(res.km_rodado_bruto)} km")
    b.metric("Só leituras confiáveis", f"{br(res.km_rodado_tratado)} km")
    c.metric("Veículos com km em dia", f"{D['km_em_dia']} / {D['frota']}")
    st.subheader("Esta apresentação é a própria solução funcionando")
    a, b, c = st.columns(3)
    with a:
        cartao("1 · Excel uma vez", "O arquivo que recebi foi tratado e virou a base única. Partes 1.1 a 1.4.")
    with b:
        cartao("2 · Depois, só a plataforma", "O engenheiro lança, a regra valida na hora. Páginas ▶ depois da 2.1.")
    with c:
        cartao("3 · Gate ao vivo", "O número muda no instante do lançamento. Plano, indicadores e pessoas em seguida.")


def diagnostico():
    st.header("1.1 Diagnóstico: a maior parte dos erros tem origem no processo")
    base = ach[ach["Tipo"] != "Oportunidade"]
    tab = (base.groupby(["Categoria", "Impacto no Gate", "Tipo"])
           .agg(Onde=("Aba", lambda s: ", ".join(sorted(set(s)))), Registros=("Regra", "size"))
           .reset_index().sort_values("Registros", ascending=False))
    a, b, c = st.columns(3)
    a.metric("Linhas com problema", f"{D['com_problema']} de {D['total_linhas']}", f"{pct:.0%}", delta_color="off")
    b.metric("Registros no log", len(base))
    c.metric("Origem total ou parcial em processo", f"{(base['Tipo'] != 'Dado').mean():.0%}",
             "vai continuar gerando erro", delta_color="off")
    st.dataframe(tab[["Categoria", "Onde", "Impacto no Gate", "Tipo", "Registros"]], hide_index=True, width=LARGO)
    escolha = st.selectbox("Ver as linhas de uma categoria", tab["Categoria"])
    st.dataframe(base[base["Categoria"] == escolha][["Aba", "Linha", "Campo", "Valor original", "Regra", "Ação"]],
                 hide_index=True, width=LARGO)
    extra = ach[ach["Tipo"] == "Oportunidade"]
    if len(extra):
        st.info("**Bônus:** " + "; ".join(f"linha {r.Linha} de {r.Aba}: {r.Regra}" for r in extra.itertuples())
                + ". Hoje ninguém enxerga isso, porque os programas estão em planilhas separadas.")
    st.caption("Dado = erro pontual que já existe. Processo = a planilha permite, então o erro volta na semana seguinte.")


def modelo():
    st.header("1.2 Modelo de dados: um veículo no centro, quatro fatos ao redor")
    st.graphviz_chart("""
    digraph { rankdir=LR; bgcolor="transparent";
      node [shape=record, style="filled,rounded", fillcolor="#fbfaf7", color="#16202b", fontname="Helvetica", fontsize=11];
      edge [color="#b45a12", fontname="Helvetica", fontsize=10, fontcolor="#b45a12"];
      P [label="{PROGRAMA|Programa_ID (PK)\\lNome · Fase\\lData do Gate\\l}"];
      V [label="{VEÍCULO|Chassi (PK)\\lCódigo PT-NN (único)\\lPrograma_ID (FK)\\lTipo · Responsável\\l}", fillcolor="#16202b", fontcolor="white"];
      S [label="{STATUS_FROTA|Chassi (FK) · Data\\lStatus · Motivo\\lPrevisão de retorno\\l}"];
      K [label="{LEITURA_KM|Chassi (FK) · Data\\lKm acumulado\\lResponsável\\l}"];
      T [label="{TESTE|T-NNN (PK) · Chassi (FK)\\lTipo (catálogo)\\lPrevista · Realizada\\lStatus calculado\\l}"];
      O [label="{OCORRÊNCIA|OC-NNNN (PK) · Chassi (FK)\\lT-NNN (FK) · Severidade\\lStatus · Abertura · Fechamento\\l}"];
      P -> V [label="1:N"]; V -> S [label="1:N"]; V -> K [label="1:N"]; V -> T [label="1:N"]; V -> O [label="1:N"];
      T -> O [label="1:N", style=dashed];
    }""", width=LARGO)
    a, b = st.columns(2)
    with a:
        cartao("Chave do veículo: o chassi",
               "Identificador físico e imutável. O código PT-NN é mantido como código de exibição, "
               "selecionado em lista e nunca digitado.")
    with b:
        cartao("Modelo enxuto",
               "O programa fica apenas no cadastro do veículo (hoje está repetido em duas abas). A ocorrência passa "
               "a se vincular ao teste. Os relatórios em PDF recebem padrão de nome com o T-NNN e um link.")
    with st.expander("🗄️ O mesmo modelo em SQL (DDL)"):
        st.code(schema_sql(), language="sql")
    st.button("Ver o banco por dentro, ao vivo →", on_click=lambda: st.session_state.update(pagina="▶ Base de dados"))
    st.subheader("O modelo já populado com os dados tratados")
    t = st.segmented_control("Tabela", list(D["tratado"].keys())[1:], default="Veiculo")
    if t:
        st.dataframe(D["tratado"][t], hide_index=True, width=LARGO)


def padroes():
    st.header("1.3 Padrões e regras: validar na porta de entrada")
    a, b = st.columns(2)
    with a:
        st.subheader("Nomenclatura")
        st.dataframe(pd.DataFrame([
            ("Veículo", "PT-NN, escolhido em lista", "PT-07"),
            ("Ocorrência", "OC-NNNN", "OC-0117"),
            ("Teste", "T-NNN + tipo de catálogo", "T-014 · Frenagem"),
            ("Data", "Campo de data (ISO)", "2026-03-18"),
            ("Status", "Lista fechada por entidade", "Aberto → Em análise → Fechado"),
            ("Pessoa", "Login corporativo", "ana.lima"),
        ], columns=["Item", "Padrão", "Exemplo"]), hide_index=True, width=LARGO)
    with b:
        st.subheader("Regras na entrada e erros que teriam barrado")
        regras = [("Veículo só da lista da Frota", ["ID fora do padrão PT-NN", "Veículo não existe"]),
                  ("Data só em campo de data", ["Data como texto", "Data em formato americano"]),
                  ("Km ≥ última leitura", ["Km regrediu", "Km em unidade errada"]),
                  (f"Salto > {br(max_km)} km/semana pede confirmação", ["Salto de"]),
                  ("Uma leitura por veículo por semana", ["Duas leituras"]),
                  ("Status só da lista", ["Status com grafia", "Status fora da lista"]),
                  ("Status do teste calculado pelas datas", ["Concluído sem data", "Status digitado diverge"]),
                  ("Fechamento ≥ abertura", ["Fechamento antes"]),
                  ("Aviso de duplicata ao abrir ocorrência", ["Provável duplicata", "ID duplicado"])]
        st.dataframe(pd.DataFrame([(n, int(ach["Regra"].str.startswith(tuple(p)).sum())) for n, p in regras],
                                  columns=["Regra", "Erros barrados nesta base"]), hide_index=True, width=LARGO)

    st.subheader("🧪 Teste uma regra ao vivo")
    o = Origem("demo", 0)
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        v = st.text_input("Veículo digitado", "Protótipo 7")
        r = VeiculoIDNormalizador().normalizar(v, o)
        st.write(f"→ **{r.valor}**", "· ⚠️ " + r.achados[0].regra if r.achados else "· ✅ já no padrão")
    with c2, st.container(border=True):
        d = st.text_input("Data digitada", "03/18/2026")
        try:
            r = DataNormalizador().normalizar(d, o, "Data")
            st.write(f"→ **{r.valor:%Y-%m-%d}**", "· ⚠️ " + r.achados[0].regra if r.achados else "· ✅")
        except (ValueError, TypeError):
            st.write("🚫 Data inválida: o campo de data não permite salvar")
    with c3, st.container(border=True):
        ant = st.number_input("Km da última leitura", value=20870.0, step=10.0)
        atu = st.number_input("Km digitado agora", value=208900.0, step=10.0)
        sem = st.number_input("Semanas desde a última", 1, 8, 1)
        hoje = date(2026, 3, 17)
        a_ = LeituraKm("PT-04", hoje - timedelta(weeks=sem), None, ant, None, None, 1)
        b_ = LeituraKm("PT-04", hoje, None, atu, None, None, 2)
        cfg = Config(max_km_semana=max_km)
        viol = next((x for regra in REGRAS_LEITURA_PADRAO if (x := regra.avaliar(b_, a_, cfg))), None)
        st.write(f"🚫 **{viol.regra}** · {viol.acao}" if viol else "✅ Leitura aceita")
    demo_banco()


CENARIOS = {
    "✅ Leitura válida": "INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-23', 14300, 'Ana Lima')",
    "Veículo fora do cadastro (PT-15)": "INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0015', '2026-03-23', 900, 'Ana Lima')",
    "Data digitada como texto": "INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '23/03/2026', 14300, 'Ana Lima')",
    "Km digitado como texto": "INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-23', '14.300 km', 'Ana Lima')",
    "Duas leituras na mesma semana": "INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-18', 13900, 'Ana Lima')",
    "Código de veículo fora do padrão": "INSERT INTO veiculo VALUES ('CHS-0099', 'PT 07', 'Alfa')",
    "Status '?' na ocorrência": "INSERT INTO ocorrencia (ocorrencia_id, chassi, descricao, status, abertura, responsavel, grupo_duplicata) VALUES ('OC-0200', 'CHS-0001', 'Falha ACC', '?', '2026-03-12', 'Ana Lima', 'OC-0200')",
    "Fechamento antes da abertura": "INSERT INTO ocorrencia (ocorrencia_id, chassi, descricao, status, abertura, fechamento, responsavel, grupo_duplicata) VALUES ('OC-0201', 'CHS-0001', 'Superaquecimento', 'Fechado', '2026-03-07', '2026-03-03', 'Ana Lima', 'OC-0201')",
    "Indisponível sem motivo": "INSERT INTO status_frota (chassi, data, status) VALUES ('CHS-0001', '2026-03-09', 'Em manutenção')",
}


def banco_demo() -> sqlite3.Connection:
    con = conectar(criar=True)
    con.executescript("""INSERT INTO parametro VALUES ('data_corte', '2026-03-31');
        INSERT INTO programa VALUES ('Alfa', 'Caminhão leve');
        INSERT INTO veiculo VALUES ('CHS-0001', 'PT-01', 'Alfa');
        INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-16', 13640, 'Ana Lima');""")
    return con


def demo_banco():
    st.subheader("🗄️ O banco recusa o dado errado")
    st.caption("Banco de teste com o PT-01 (chassi CHS-0001) e uma leitura em 16/03. Escolha uma tentativa ou edite o SQL.")
    c = st.selectbox("Tentativa", list(CENARIOS))
    sql = st.text_area("SQL", CENARIOS[c], height=80, key=f"sql_{c}")
    if st.button("Executar no banco", type="primary"):
        con = banco_demo()
        try:
            con.execute(sql)
            st.success("✅ Aceito: o dado entrou na base.")
        except sqlite3.IntegrityError as e:
            st.error(f"🚫 Recusado pelo banco: {e}")
        except sqlite3.Error as e:
            st.warning(f"SQL inválido: {e}")
        finally:
            con.close()
    st.caption("Km menor que a leitura anterior e salto por semana comparam linhas diferentes: não cabem em CHECK. "
               "Essas ficam na validação de entrada (acima).")


def tratamento():
    st.header("1.4 Carga na base: antes e depois, e as duas camadas de defesa")
    cols = st.columns(4)
    for c, (n, t, x) in zip(cols, [("1", "Cópia bruta", "Original intocado, sempre rastreável"),
                                   ("2", "Padronização", "ID, data, status e nome corrigidos automaticamente"),
                                   ("3", "Quarentena", "O que muda o sentido vai ao dono, com sugestão"),
                                   ("4", "Base tratada", "Com log apontando a linha de origem")]):
        with c:
            cartao(f"{n} · {t}", x)
    st.subheader("Demonstração: a aba Ocorrências antes e depois")
    a, b = st.columns(2)
    a.caption("ANTES (como chegou)")
    a.dataframe(D["bruto"]["Ocorrencias"].astype("string"), hide_index=True, width=LARGO)  # mostra como foi digitado
    b.caption("DEPOIS (padronizada, com grupo de duplicata)")
    b.dataframe(D["tratado"]["Ocorrencia"].drop(columns=["Linha_origem"]), hide_index=True, width=LARGO)
    st.subheader("Quarentena de km: nada é corrigido sozinho")
    st.dataframe(D["quarentena"], hide_index=True, width=LARGO)
    st.subheader("Carga na base única (SQLite): duas camadas de defesa")
    bd = D["banco"]
    pend = bd["pendencias"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Linhas aceitas pelo banco", int(bd["contagens"]["aceitas"].sum()))
    m2.metric("Barradas pelo domínio (quarentena)", int((pend["barrado_por"] == "Domínio").sum()))
    m3.metric("Barradas pelo banco (constraints)", int((pend["barrado_por"] == "Banco").sum()))
    st.dataframe(pend[pend["barrado_por"] == "Banco"], hide_index=True, width=LARGO)
    g1, g2 = st.columns(2)
    g1.caption("Gate calculado em SQL (vw_gate_programa)")
    g1.dataframe(bd["gate"], hide_index=True, width=LARGO)
    g2.caption("Gate calculado no domínio Python")
    g2.dataframe(gate[["Programa", "Km rodado", "Falhas abertas", "Testes concluídos", "Testes atrasados"]],
                 hide_index=True, width=LARGO)
    st.caption(f"Km e testes batem. Falhas: SQL mostra {int(bd['gate']['falhas_abertas'].sum())} confirmadas; "
               f"o domínio conta {res.falhas_abertas_depois} porque inclui as que estão com status '?', "
               "que o banco recusou até o dono informar o status.")
    a, b = st.columns([3, 1])
    with a:
        cartao("Para não voltar",
               "O Excel entra uma vez, como carga inicial. O que foi barrado vira pendência com o nome do dono. "
               "Daí em diante ninguém manda planilha: cada engenheiro lança na plataforma, validado na hora.")
        st.button("Ver as pendências de cada dono →", on_click=lambda: st.session_state.update(pagina="▶ Minhas pendências"))
    b.download_button("⬇️ Base tratada (.xlsx)", D["xlsx"], "Case_Dados_Tratados.xlsx", width=LARGO)
    b.download_button("⬇️ Base SQLite (.db)", D["banco"]["db"], "validacao.db", width=LARGO)


def fluxo():
    st.header("2.1 Fluxo do Gate Review: do copia-e-cola para a leitura do painel")
    a, b = st.columns(2)
    with a:
        st.subheader("Hoje · 2 pessoas × 3 dias")
        st.graphviz_chart("""
        digraph { rankdir=TB; bgcolor="transparent"; node [shape=box, style="filled,rounded", fillcolor="#fbfaf7", fontname="Helvetica", fontsize=11];
          F [label="5 fontes: Excel, planilha de km,\\nSharePoint, e-mail, PDF"]; C [label="Copiar, colar, conciliar"];
          S [label="Montar slides do zero"]; G [label="Gate: discute qual número vale", fillcolor="#f6d8bd"];
          F -> C [label=" espera", fontcolor="#b45a12"]; C -> S [label=" transporte", fontcolor="#b45a12"];
          S -> G [label=" superprocesso", fontcolor="#b45a12"]; G -> C [label=" retrabalho", style=dashed, color="#b45a12", fontcolor="#b45a12"];
        }""", width=LARGO)
    with b:
        st.subheader("Desejado · horas, não dias")
        st.graphviz_chart("""
        digraph { rankdir=TB; bgcolor="transparent"; node [shape=box, style="filled,rounded", fillcolor="#fbfaf7", fontname="Helvetica", fontsize=11];
          X [label="Excel: só a carga inicial", style="dashed,rounded", fillcolor="#f4f2ee", fontcolor="#5b6573"];
          E [label="Engenheiro lança\\nna plataforma"]; L [label="Logística atualiza\\nstatus na plataforma"];
          B [label="Base única\\n(regras Python + constraints do banco)"];
          P [label="Gate ao vivo\\n+ pendências por dono"];
          G [label="Gate: revisar e decidir", fillcolor="#16202b", fontcolor="white"];
          X -> B [style=dashed, label=" 1ª vez", fontcolor="#5b6573"]; E -> B; L -> B;
          B -> P [label=" na hora", fontcolor="#b45a12"]; P -> G;
        }""", width=LARGO)
    st.dataframe(pd.DataFrame([
        ("Espera", "Disponibilidade chega por e-mail, quando chega"),
        ("Transporte", "Copiar e colar entre 5 fontes"),
        ("Superprocesso", "Slides refeitos do zero a cada Gate"),
        ("Defeito", f"{pct:.0%} das linhas com algum problema"),
        ("Retrabalho", "Número contestado na reunião volta para conferência"),
    ], columns=["Desperdício (Lean)", "Onde aparece"]), hide_index=True, width=LARGO)
    st.caption("O maior desperdício não são os 3 dias de preparo: é a reunião gasta discutindo número em vez de decidir.")
    st.subheader("O fluxo desejado já funciona: Excel uma vez, depois só a plataforma")
    x, y, z = st.columns(3)
    x.info("**1 · Carga inicial**  \nO Excel é tratado e vira a base única")
    y.info("**2 · Lançamento**  \nO engenheiro lança; domínio e banco validam na hora")
    z.success("**3 · Gate ao vivo**  \nO número muda no instante do lançamento")
    st.subheader("Do protótipo à produção: o que muda")
    st.dataframe(pd.DataFrame([
        ("Lançamento validado", "Formulário desta plataforma", "Nada: mesma tela, com login corporativo"),
        ("Status da frota (logística)", "Tela de status da frota", "Nada (Power Automate só se a logística insistir no e-mail)"),
        ("Regras de qualidade", "Python, com testes automatizados", "Nada: o mesmo código"),
        ("Base única", "SQLite", "Banco SQL corporativo, com o mesmo DDL"),
        ("Gate + qualidade", "Gate ao vivo", "Nada (Power BI opcional, lendo o mesmo banco)"),
        ("Onde roda", "Docker no meu notebook", "Container no ambiente Python corporativo"),
    ], columns=["Parte", "Hoje (protótipo)", "Em produção, o que muda"]), hide_index=True, width=LARGO)
    st.caption("Mudam apenas a hospedagem, o banco de dados e a autenticação. Premissa a confirmar com a TI: existe hospedagem Python corporativa "
               "(Python/SQL estão na lista de homologadas). Plano B, se não existir: as mesmas regras, com entrada em "
               "Power Apps e painel em Power BI.")
    st.button("Ver o fluxo funcionando →", on_click=lambda: st.session_state.update(pagina="▶ Lançar dados"))


def plano():
    st.header("2.2 Plano de 90 dias: primeiro confiança no dado, depois o painel")
    cols = st.columns(3)
    blocos = [("30 dias · Base", ["Padrões e status aprovados pelo gestor", "Hospedagem Python e banco confirmados com a TI",
                                  "Carga inicial; pendências devolvidas aos donos", "Piloto: 1 programa e 1 engenheiro “campeão”"]),
              ("60 dias · Piloto", ["Plataforma no ar para o programa piloto", "Lembrete semanal de km automático",
                                    "Logística atualiza o status na plataforma", "Gate ao vivo + painel de qualidade"]),
              ("90 dias · Escala", ["Os 3 programas na plataforma", "Plano de testes com status calculado",
                                    "1º Gate Review direto do Gate ao vivo", "Medir indicadores e ajustar"])]
    for c, (t, itens) in zip(cols, blocos):
        with c, st.container(border=True):
            st.subheader(t)
            st.markdown("\n".join(f"- {i}" for i in itens))
    a, b = st.columns(2)
    with a:
        with st.container(border=True):
            st.markdown("**Critérios da sequência**")
            st.markdown("1. **Qualidade antes da visualização:** um painel sobre dados inconsistentes reproduz a divergência atual.\n"
                        "2. **Entrega desde o primeiro mês:** em 30 dias, cada responsável recebe a lista de inconsistências dos seus dados.\n"
                        "3. **Escopo compatível com uma pessoa:** um programa piloto completo antes de escalar para os três.")
            st.caption("As regras de validação já estão implementadas e testadas neste protótipo, o que reduz o risco das etapas seguintes.")
    with b:
        cartao("Fora do escopo dos 90 dias",
               "Conteúdo dos relatórios em PDF (apenas padrão de nome e link), IA, integração com sistemas corporativos "
               "e aplicativo mobile. Esses itens dependem de uma base confiável e entram na etapa seguinte.")


def indicadores():
    st.header("2.3 Indicadores: três números para provar que funcionou")
    k = [("⏱️ Tempo de preparo do Gate", "2 pessoas × 3 dias (≈ 48 h)", "≤ 4 h",
          "Horas registradas nos 2 próximos Gates", "Eficiência"),
         ("🎯 Números contestados no Gate", f"{len(res.falhas_abertas_antes)} versões da mesma métrica "
          f"({min(res.falhas_abertas_antes.values())} a {max(res.falhas_abertas_antes.values())} falhas)",
          "Zero: um número, uma fonte", "Contestações registradas em ata", "Confiança"),
         ("🧪 Qualidade na entrada", f"{pct:.0%} das linhas com problema; {D['km_em_dia']} de {D['frota']} com km em dia",
          "< 5% em quarentena; ≥ 95% km em dia", "Painel de qualidade, automático e semanal", "Saúde do dado")]
    for c, (t, base, meta, como, tipo) in zip(st.columns(3), k):
        with c, st.container(border=True):
            st.subheader(t)
            st.caption(tipo.upper())
            st.markdown(f"**Linha de base:** {base}\n\n**Meta:** {meta}\n\n**Como medir:** {como}")
    st.caption("Linhas de base 2 e 3 calculadas nesta base. A de tempo vem do briefing; a meta de 4 h é premissa a validar com o gestor. "
               "A medição da qualidade já existe: a página ▶ Gate ao vivo calcula km em dia e pendências a cada lançamento.")


def adesao():
    st.header("2.4 Adesão: reduzir o retrabalho, preservando a autonomia do engenheiro")
    c = st.columns(2)
    for i, (t, x) in enumerate([
        ("Responsabilidade preservada", "Cada registro identifica o engenheiro responsável. "
                                       "Nenhuma correção é feita sem a confirmação dele."),
        ("Transição gradual", "A planilha atual entra na carga inicial, com o responsável identificado em cada linha. "
                              "A migração para a plataforma acontece à medida que ela se mostra confiável."),
        ("Engenheiro de referência no piloto", "A tela de lançamento é desenhada com um engenheiro do programa piloto, "
                                               "que apresenta o resultado aos colegas."),
        ("Diretriz da gestão", "No Gate Review, a referência é o painel. O painel de qualidade é retorno individual, "
                               "não comparação entre pessoas.")]):
        with c[i % 2]:
            cartao(t, x)
    st.subheader("Cada responsável recebe a própria lista de pendências")
    pend = BASE.pendencias()
    resumo = pend.groupby("responsavel").size().rename("pendências").reset_index()
    a, b = st.columns([1, 2])
    a.dataframe(resumo.rename(columns={"responsavel": "Responsável"}), hide_index=True, width=LARGO)
    with b:
        cartao("Por que isso favorece a adesão",
               "Cada responsável vê apenas os seus itens, com sugestão de correção. "
               "A resolução leva minutos e não depende de reuniões de acompanhamento.")
        st.button("Abrir as pendências de um engenheiro →",
                  on_click=lambda: st.session_state.update(pagina="▶ Minhas pendências"))


def ia():
    st.header("2.5 Inteligência artificial: IA para sugerir, regra para decidir")
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.subheader("✅ Onde entra")
        st.markdown("- Sugerir duplicatas e agrupar falhas parecidas\n- Achar padrão entre programas\n"
                    "- Extrair veículo, teste e data dos PDFs\n- Rascunho do resumo executivo do Gate")
    with b, st.container(border=True):
        st.subheader("🚫 Onde não entra")
        st.markdown("- Calcular número oficial: regra fixa e auditável\n- Corrigir dado sem o dono confirmar\n"
                    "- Decidir o Gate\n- Dado confidencial fora de ferramenta homologada")
    st.subheader("Exemplo ao vivo: sugestões para um humano confirmar")
    sug = ach[ach["Regra"].str.startswith(("Provável duplicata", "Mesma falha"))]
    st.dataframe(sug[["Aba", "Linha", "Valor original", "Regra", "Ação"]], hide_index=True, width=LARGO)
    st.caption("Aqui a sugestão vem de similaridade de texto simples; com IA, o mesmo fluxo pega casos que não "
               "compartilham palavras. A decisão continua com o dono.")
    with st.container(border=True):
        st.markdown("**Como usei IA neste case:** para acelerar a leitura das abas e escrever o código. "
                    "Validei cada achado na planilha original (todo registro aponta a linha de origem), escrevi "
                    "testes automatizados e corrigi uma regra que gerava falso alerta de km no PT-07.")


def riscos():
    st.header("Premissas e riscos")
    a, b = st.columns(2)
    with a:
        st.subheader("Premissas")
        st.dataframe(pd.DataFrame([
            ("Data ambígua segue dd/mm", "Inverteria dia e mês em 12 datas"),
            ("Data prevista = data de conclusão", "Mudaria quem está atrasado"),
            (f"Corte do Gate em {res.corte:%d/%m/%Y}", "Mudaria quem está sem leitura"),
            (f"Até {br(max_km)} km/semana é plausível", "Mude na barra lateral e veja o efeito"),
            ("Chassi é único e não muda", "Base do modelo inteiro"),
            ("PT-13, 14 e 15 podem existir sem cadastro", "Confirmar com a logística: cadastrar, não descartar"),
            ("Há hospedagem Python corporativa", "Plano B: mesmas regras, entrada em Power Apps e painel em Power BI"),
        ], columns=["Premissa", "Se estiver errada…"]), hide_index=True, width=LARGO)
    with b:
        st.subheader("Riscos → mitigação")
        st.dataframe(pd.DataFrame([
            ("Baixa adesão", "Piloto, campeão e regra do gestor"),
            ("Projeto de uma pessoa só", "Código testado, em container e documentado no Azure DevOps"),
            ("Logística seguir no e-mail", "Tela de status simples; Power Automate se for preciso"),
            ("SQLite com muita gente ao mesmo tempo", "Em produção, banco SQL corporativo com o mesmo DDL"),
            ("Protótipo sem login", "Login corporativo em produção; a base já registra quando cada dado entrou"),
        ], columns=["Risco", "Mitigação"]), hide_index=True, width=LARGO)
    st.subheader("As duas premissas numéricas (mude na barra lateral ⚙️)")
    st.dataframe(pd.DataFrame([
        ("Limite de km por semana", f"{br(max_km)} km",
         "Um veículo em 1 turno de teste roda ≈ 8 h × 60 km/h × 6 dias ≈ 2.900 km/semana. Na base, o real vai até ≈ 1.700; o erro, a 188 mil",
         f"Hoje: {br(res.km_rodado_tratado)} km confiáveis. Abaixo de ≈ 1.700, leituras reais do PT-07 viram suspeitas"),
        ("Dias sem leitura", f"{dias} dias",
         "O km deve ser lançado toda semana",
         f"Hoje: {D['km_em_dia']} de {D['frota']} veículos em dia na data de corte ({res.corte:%d/%m/%Y})"),
    ], columns=["Premissa", "Valor", "Por que esse valor", "Efeito agora"]), hide_index=True, width=LARGO)


NOTAS = {
    "👤 About me": "≈ 1 min 30. Hi, I'm Matheus, an electrical engineer from IME, and I live here in Resende. "
                  "My path has two lines that keep meeting: engineering and software. At IME I worked on robotics "
                  "and simulation; then I was a data science intern, building churn models in Python and Power BI "
                  "dashboards. As an Army engineer in Belém I did electrical projects and data analysis, and today "
                  "I inspect a medium-voltage network upgrade here in Resende. On the side I build Dominica, a "
                  "platform for engineering contracts, in .NET and React.",
    "👤 Why this role": "≈ 1 min 30. Four things this role asks for, and where I have done them. Data that drives "
                        "decisions: I analysed the energy consumption of 17 Army sites in three states for the move "
                        "to the free market; it was a team project, and the first bills came 18 to 30 percent lower. "
                        "Automation: scripts that replaced manual spreadsheet work. Tools: Dominica. AI and analytics: "
                        "ML models as an intern, and today AI every day, always validated with tests. I have been the "
                        "engineer receiving messy data; I want to be the one who fixes it.",
    "Início": '0:45 · ATO 1, O PROBLEMA. "Vou apresentar em cima da própria solução: todo número aqui é calculado agora, do Excel que recebi. Começo com uma pergunta simples: quantas falhas estão abertas? A planilha dá quatro respostas: 9, 11, 16 ou 12. E o km da frota varia 15 vezes conforme quem soma." → "Por que isso acontece?"',
    "1.1 Diagnóstico": '1:00 · "Encontrei 80 problemas em 52% das linhas. O ponto principal: quase todos vêm do processo, não de quem digita. Texto livre, nenhuma validação, status digitado à mão. Se eu só limpar, o erro volta na semana seguinte." Abra \'Km inconsistente\'. Bônus em 1 frase: a falha CAN aparece em dois programas. → "Então a solução precisa começar pelo modelo."',
    "1.2 Modelo de dados": '0:50 · "Um veículo no centro, quatro fatos ao redor. A chave é o chassi, porque é físico e não muda; o PT-NN vira código escolhido em lista. Cada regra virou restrição no banco." → "E o histórico que já existe?"',
    "1.3 Padrões e regras": "≈ 40 s. Cada regra corresponde a um erro real. Duas camadas: o banco barra o que é de "
                            "uma linha; o domínio barra o que compara linhas. Guarde a demo do banco para a arguição.",
    "1.4 Tratamento": '1:20 · "Esta é a parte que mais importa. Três regras: padronizo sozinho o que é seguro, pergunto ao dono o que muda o sentido, e nunca apago." Mostre a faixa dos 7 passos e abra a aba ④ com o PT-07: "comparo cada leitura com a última BOA; senão um erro contaminaria o resto". Feche na aba ⑥: "16 viram 12, e cada uma que saiu tem motivo." → "Agora a segunda pergunta do gestor: o que muda no Gate?"',
    "2.1 Fluxo do Gate": "≈ 40 s. O maior desperdício é a reunião discutindo número. O fluxo desejado é esta "
                         "plataforma: para ir a produção muda só onde roda, o banco e o login. Clique em 'Ver o fluxo funcionando'.",
    "2.1 Impacto no Gate Review": '1:00 · ATO 2, A MUDANÇA. "Hoje preparar o Gate é consolidar planilhas: duas pessoas, três dias. Com a base única, vira verificar a prontidão. O programa só vai ao Gate com o dado pronto, e a reunião discute risco, não número." → "Deixa eu mostrar funcionando."',
    "▶ Pacote do Gate": '0:40 · Programa Alfa: "A plataforma diz se ele está pronto e o que impede, com o nome de quem resolve. O material da reunião sai em um clique. É o que hoje leva três dias." → "Como eu chego nisso em 90 dias, sozinho?"',
    "▶ Base de dados": "Na arguição. Mostre o diagrama lido do próprio banco (o veículo no centro), a tabela que "
                       "veio do Excel × o que entrou pela plataforma, e rode um SELECT ao vivo. Se pedirem, tente um "
                       "DELETE: a conexão só leitura recusa.",
    "▶ Lançar dados": '1:00 · DEMO. Como Ana Lima, aba Quilometragem: PT-01, 13.000 km → barrado (\'km regrediu\'). Corrija para 14.300 → entra. "O dado nasce validado, na origem." → "E o efeito no Gate é imediato."',
    "▶ Minhas pendências": "Na arguição. Como Patrícia Rocha: aceitar a sugestão do PT-04 com um clique.",
    "▶ Gate ao vivo": "≈ 20 s. O km do Alfa mudou. Este é o Gate em horas, não dias. Reinicie a base ANTES da entrevista.",
    "2.2 Plano de 90 dias": '1:00 · ATO 3, O PLANO. "Três critérios: qualidade antes de painel, entrega desde o primeiro mês, e um programa piloto antes de escalar, porque sou uma pessoa só." Cite o que fica de fora em 1 frase. → "E como saber se funcionou?"',
    "2.3 Indicadores": '0:50 · "Três números: tempo de preparo, de 3 dias para 4 horas; números contestados no Gate, de quatro versões para uma; e qualidade na entrada. O segundo é o que o gestor sente." → "Nada disso funciona sem os engenheiros."',
    "2.4 Adesão": '0:40 · "O engenheiro mantém controle próprio porque hoje é a única fonte em que confia. Não peço para largar: faço a base ser mais confiável que a planilha dele. Cada um recebe a própria lista, não um ranking." → "Para fechar, o que assumi."',
    "2.5 Inteligência artificial": "≈ 30 s. IA sugere, regra decide. Conte como usou IA e como validou: linha de "
                                   "origem em cada achado e testes automatizados.",
    "Premissas e riscos": '0:45 · FECHO. "As premissas que eu mais validaria: os veículos PT-13, 14 e 15, e se existe hospedagem Python na empresa; se não existir, o plano B usa Power Apps e Power BI com as mesmas regras." IA em 1 frase: "IA sugere, regra decide." Termine com: "Um número só no Gate Review." e pare.',
}


def reiniciar():
    garantir_base(BASE_DB, conteudo, reiniciar=True, config=CFG)
    for k in [k for k in st.session_state if k.startswith(("msg_", "conf_"))]:
        del st.session_state[k]


{"👤 About me": sobre_mim, "👤 Why this role": por_que_vaga, "Início": inicio, "1.1 Diagnóstico": diagnostico, "1.2 Modelo de dados": modelo,
 "1.3 Padrões e regras": padroes, "1.4 Tratamento": lambda: tratamento_ui.pagina(D, res, CFG), "1.4 Carga na base": tratamento, "2.1 Fluxo do Gate": fluxo,
 "▶ Lançar dados": lambda: plataforma.lancar(BASE, CFG),
 "▶ Minhas pendências": lambda: plataforma.pendencias(BASE, CFG),
 "2.1 Impacto no Gate Review": lambda: gate_ui.impacto(
     (len(res.falhas_abertas_antes) + 1, min(res.falhas_abertas_antes.values()), max(res.falhas_abertas_antes.values())),
     pct, D["km_em_dia"], D["frota"]),
 "▶ Gate ao vivo": lambda: plataforma.gate_ao_vivo(BASE, dias, reiniciar),
 "▶ Pacote do Gate": lambda: gate_ui.pacote(BASE, dias),
 "▶ Base de dados": lambda: banco_ui.pagina(BASE),
 "2.2 Plano de 90 dias": plano, "2.3 Indicadores": indicadores, "2.4 Adesão": adesao,
 "2.5 Inteligência artificial": ia, "Premissas e riscos": riscos}[st.session_state["pagina"]]()
if NOTAS_ON and st.session_state["pagina"] in NOTAS:
    st.info("🗣️ " + NOTAS[st.session_state["pagina"]])
rodape()
