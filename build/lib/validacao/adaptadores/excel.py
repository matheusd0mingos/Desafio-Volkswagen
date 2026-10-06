"""Adaptadores Excel. Único lugar que conhece pandas/openpyxl."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from ..aplicacao.portas import BaseBruta, ResultadoTratamento


def _para_python(v):
    if v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


class ExcelFonte:
    ABAS = ("Frota", "Quilometragem", "Ocorrencias", "Plano_Testes")

    def __init__(self, caminho: str) -> None:
        self._caminho = caminho

    def ler(self) -> BaseBruta:
        abas = pd.read_excel(self._caminho, sheet_name=list(self.ABAS))
        linhas = {k: [{c: _para_python(v) for c, v in r.items()} for r in df.astype(object).to_dict("records")]
                  for k, df in abas.items()}
        return BaseBruta(linhas["Frota"], linhas["Quilometragem"], linhas["Ocorrencias"], linhas["Plano_Testes"])


class ExcelRepositorio:
    def __init__(self, caminho: str) -> None:
        self._caminho = caminho

    def salvar(self, r: ResultadoTratamento) -> None:
        s = r.resumo
        resumo = pd.DataFrame(
            [("Falhas abertas — " + k, v) for k, v in s.falhas_abertas_antes.items()] +
            [("Falhas abertas — após tratamento", s.falhas_abertas_depois),
             ("Km rodado no período — bruto", s.km_rodado_bruto),
             ("Km rodado no período — só leituras OK", s.km_rodado_tratado),
             ("Registros no log de qualidade", s.total_achados),
             ("Data de corte usada (premissa)", f"{s.corte:%d/%m/%Y}")], columns=["Indicador", "Valor"])
        veic = pd.DataFrame([{"Veiculo_ID": v.id, "Chassi": v.chassi, "Programa": v.programa, "Tipo": v.tipo,
                              "Status": v.status, "Atualizado_em": v.atualizado_em} for v in r.veiculos])
        km = pd.DataFrame([{"Veiculo_ID": l.veiculo, "Data": l.data, "Km_acumulado": l.km, "Km_sugerido": l.km_sugerido,
                            "Responsavel": l.responsavel, "Observação": l.observacao, "Qualidade": l.qualidade.value,
                            "Linha_origem": l.linha}
                           for l in sorted(r.leituras, key=lambda l: (l.veiculo, l.data, l.linha))])
        oc = pd.DataFrame([{"Ocorrencia_ID": o.id, "Veiculo_ID": o.veiculo, "Descrição": o.descricao, "Status": o.status,
                            "Abertura": o.abertura, "Fechamento": o.fechamento, "Responsavel": o.responsavel,
                            "Grupo_duplicata": o.grupo, "Linha_origem": o.linha} for o in r.ocorrencias])
        te = pd.DataFrame([{"Teste_ID": t.id, "Veiculo_ID": t.veiculo, "Teste": t.nome, "Data prevista": t.prevista,
                            "Data realizada": t.realizada, "Status_digitado": t.status_digitado,
                            "Status_calculado": t.status_calculado, "Engenheiro": t.engenheiro, "Linha_origem": t.linha}
                           for t in r.testes])
        log = pd.DataFrame([{"Aba": a.origem.aba, "Linha_origem": a.origem.linha, "Campo": a.campo,
                             "Valor_original": a.valor_original, "Regra": a.regra, "Severidade": a.severidade.value,
                             "Acao": a.acao} for a in r.achados])
        for df in (veic, km, oc, te):
            for c in df.columns:
                if c in {"Atualizado_em", "Data", "Abertura", "Fechamento", "Data prevista", "Data realizada"}:
                    df[c] = pd.to_datetime(df[c])
        with pd.ExcelWriter(self._caminho, engine="openpyxl", datetime_format="DD/MM/YYYY", date_format="DD/MM/YYYY") as w:
            for nome, df in {"Resumo": resumo, "Veiculo": veic, "Leitura_Km": km, "Ocorrencia": oc,
                             "Teste": te, "Log_Qualidade": log}.items():
                df.to_excel(w, sheet_name=nome, index=False)
                ws = w.sheets[nome]
                for col in ws.columns:
                    ws.column_dimensions[col[0].column_letter].width = min(max(len(str(c.value or "")) for c in col) + 2, 60)
                ws.freeze_panes = "A2"
