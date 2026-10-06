"""Camada de dados do painel: roda o caso de uso e prepara tabelas para exibição."""
from __future__ import annotations

import io
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from validacao.adaptadores.excel import ExcelFonte, ExcelRepositorio
from validacao.adaptadores.composto import RepositorioComposto
from validacao.adaptadores.memoria import RepositorioEmMemoria
from validacao.adaptadores.sqlite.repositorio import SqliteRepositorio
from validacao.aplicacao.tratar_base import TratarBaseDeValidacao
from validacao.dominio.modelos import Config, Qualidade
from validacao.dominio.servicos import AnalisadorOcorrencias, km_rodado

# regra (prefixo) → (categoria, impacto no Gate, tipo). Ordem importa: prefixos mais específicos primeiro.
CATEGORIAS = [
    ("ID fora do padrão PT-NN", "ID do veículo fora do padrão", "Veículo some ou duplica no consolidado", "Processo"),
    ("Veículo não existe na Frota", "Veículo fora do cadastro", "Km, falhas e testes órfãos", "Processo"),
    ("Data em formato americano", "Datas em formatos mistos", "Ordem e semana erradas; dia e mês invertidos", "Processo"),
    ("Data como texto", "Datas em formatos mistos", "Ordem e semana erradas; dia e mês invertidos", "Processo"),
    ("Salto de", "Km inconsistente", "Km da frota inflado", "Dado + Processo"),
    ("Km em unidade errada", "Km inconsistente", "Km da frota inflado", "Dado + Processo"),
    ("Km regrediu", "Km inconsistente", "Km da frota inflado", "Dado + Processo"),
    ("Km vazio", "Km inconsistente", "Km da frota inflado", "Dado + Processo"),
    ("Duas leituras", "Km inconsistente", "Km da frota inflado", "Dado + Processo"),
    ("Sem leitura válida", "Km desatualizado", "O Gate olha uma foto velha da frota", "Processo"),
    ("Status com grafia", "Status sem padrão", "Várias contagens de falhas abertas", "Processo"),
    ("Status fora da lista", "Status sem padrão", "Várias contagens de falhas abertas", "Processo"),
    ("ID duplicado", "ID de ocorrência inconsistente", "Não dá para rastrear nem contar", "Processo"),
    ("Ocorrência sem ID", "ID de ocorrência inconsistente", "Não dá para rastrear nem contar", "Processo"),
    ("ID fora do padrão", "ID de ocorrência inconsistente", "Não dá para rastrear nem contar", "Processo"),
    ("Provável duplicata", "Ocorrência duplicada", "Falhas abertas infladas", "Processo"),
    ("Fechamento antes", "Datas incoerentes", "Tempo de solução negativo", "Dado"),
    ("Fechada sem data", "Datas incoerentes", "Tempo de solução indefinido", "Dado"),
    ("Concluído sem data", "Status do teste contradiz as datas", "Avanço do plano irreal", "Processo"),
    ("Status digitado diverge", "Status do teste contradiz as datas", "Avanço do plano irreal", "Processo"),
    ("Nome fora do padrão", "Responsável escrito de vários jeitos", "Não dá para filtrar nem cobrar por dono", "Processo"),
    ("Nome de teste fora", "Teste sem catálogo", "Não agrega por tipo de teste", "Processo"),
    ("Veículo indisponível", "Indisponível sem motivo nem previsão", "O Gate não sabe quando o veículo volta", "Processo"),
    ("Programa diverge", "Programa repetido e divergente", "Veículo contado no programa errado", "Processo"),
    ("Mesma falha de", "Mesma falha em veículos diferentes", "Possível falha sistêmica, invisível hoje", "Oportunidade"),
]


def categorizar(regra: str) -> tuple[str, str, str]:
    for prefixo, cat, impacto, tipo in CATEGORIAS:
        if regra.startswith(prefixo):
            return cat, impacto, tipo
    return "Outros", "—", "—"


@st.cache_data(show_spinner="Tratando a base…")
def tratar(conteudo: bytes, max_km_semana: int, dias_sem_leitura: int) -> dict:
    cfg = Config(max_km_semana=max_km_semana, dias_sem_leitura=dias_sem_leitura)
    tmp = Path(tempfile.mkdtemp()) / "validacao.db"
    repo = RepositorioComposto(RepositorioEmMemoria(), SqliteRepositorio(tmp))
    r = TratarBaseDeValidacao(ExcelFonte(io.BytesIO(conteudo)), repo, cfg).executar()
    with sqlite3.connect(tmp) as con:
        banco = {
            "contagens": pd.read_sql("""SELECT 'veiculo' AS tabela, COUNT(*) AS aceitas FROM veiculo UNION ALL
                                        SELECT 'status_frota', COUNT(*) FROM status_frota UNION ALL
                                        SELECT 'leitura_km', COUNT(*) FROM leitura_km UNION ALL
                                        SELECT 'teste', COUNT(*) FROM teste UNION ALL
                                        SELECT 'ocorrencia', COUNT(*) FROM ocorrencia""", con),
            "pendencias": pd.read_sql("SELECT tabela, linha_origem, chave, motivo, barrado_por FROM pendencia", con),
            "gate": pd.read_sql("SELECT * FROM vw_gate_programa", con),
        }
    banco["db"] = tmp.read_bytes()
    bruto = pd.read_excel(io.BytesIO(conteudo), sheet_name=["Frota", "Quilometragem", "Ocorrencias", "Plano_Testes"])

    xlsx = io.BytesIO()
    ExcelRepositorio(xlsx).salvar(r)

    prog = {v.id: v.programa for v in r.veiculos}
    resp_veiculo = {l.veiculo: l.responsavel for l in r.leituras if l.responsavel}
    dono = {("Quilometragem", l.linha): l.responsavel for l in r.leituras}
    dono |= {("Ocorrencias", o.linha): o.responsavel for o in r.ocorrencias}
    dono |= {("Plano_Testes", t.linha): t.engenheiro for t in r.testes}

    linhas = []
    for a in r.achados:
        cat, impacto, tipo = categorizar(a.regra)
        linhas.append({"Categoria": cat, "Aba": a.origem.aba, "Linha": str(a.origem.linha), "Campo": a.campo,
                       "Valor original": a.valor_original, "Regra": a.regra, "Severidade": a.severidade.value,
                       "Ação": a.acao, "Impacto no Gate": impacto, "Tipo": tipo,
                       "Responsável": "Logística" if a.origem.aba == "Frota"
                       else dono.get((a.origem.aba, a.origem.linha)) or resp_veiculo.get(a.valor_original, "—")})
    achados = pd.DataFrame(linhas)

    gate = []
    for p in sorted(set(prog.values())):
        ids = frozenset(v for v, pp in prog.items() if pp == p)
        oc = [o for o in r.ocorrencias if o.veiculo in ids]
        te = [t for t in r.testes if t.veiculo in ids]
        gate.append({"Programa": p, "Veículos": len(ids),
                     "Disponíveis": sum(v.status == "Disponível" for v in r.veiculos if v.id in ids),
                     "Km rodado": km_rodado(l for l in r.leituras if l.veiculo in ids),
                     "Falhas abertas": AnalisadorOcorrencias.abertas_unicas(oc, ids),
                     "Testes concluídos": sum(t.status_calculado == "Concluído" for t in te),
                     "Testes atrasados": sum(t.status_calculado == "Atrasado" for t in te)})

    total_linhas = sum(len(df) for df in bruto.values())
    com_problema = achados[(achados["Linha"] != "-") & (achados["Severidade"] != "Info")][["Aba", "Linha"]] \
        .drop_duplicates().shape[0]
    atrasados = achados[achados["Regra"].str.startswith("Sem leitura")]["Valor original"].nunique()

    tratado = pd.read_excel(io.BytesIO(xlsx.getvalue()), sheet_name=None)
    for df in tratado.values():                       # datas sem "00:00:00" na tela
        for c in df.select_dtypes("datetime").columns:
            df[c] = df[c].dt.date
    quarentena = pd.DataFrame([{"Veículo": l.veiculo, "Data": l.data, "Km digitado": l.km,
                                "Km sugerido": l.km_sugerido, "Responsável": l.responsavel, "Linha": l.linha}
                               for l in r.leituras if l.qualidade is Qualidade.QUARENTENA])
    return {"resumo": r.resumo, "achados": achados, "gate": pd.DataFrame(gate), "bruto": bruto,
            "tratado": tratado, "quarentena": quarentena, "xlsx": xlsx.getvalue(),
            "total_linhas": total_linhas, "banco": banco, "com_problema": com_problema,
            "frota": len(r.veiculos), "km_em_dia": len(r.veiculos) - atrasados}
