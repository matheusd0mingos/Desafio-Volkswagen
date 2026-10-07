"""Adaptador da base em operação (SQLite). Implementa a porta BaseOperacional + consultas de leitura."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from ...aplicacao.portas import RecusadoPeloBanco
from ...dominio.modelos import LeituraKm, Ocorrencia
from .repositorio import conectar, inserir

# constraint → mensagem para o engenheiro (o banco fala técnico; a tela fala português)
MENSAGENS = {
    "FOREIGN KEY": "Veículo ou teste não existe no cadastro.",
    "data_iso": "Data inválida.",
    "km_numerico_positivo": "Km precisa ser um número maior ou igual a zero.",
    "leitura_km.chassi, leitura_km.semana": "Já existe leitura deste veículo nesta semana.",
    "leitura_km.chassi, leitura_km.data": "Já existe leitura deste veículo nesta data.",
    "status_ocorrencia_lista": "Status precisa ser Aberto, Em análise ou Fechado.",
    "fechamento_apos_abertura": "A data de fechamento não pode ser anterior à abertura.",
    "fechado_tem_data": "Ocorrência fechada precisa de data de fechamento.",
    "indisponivel_exige_motivo": "Veículo indisponível precisa de motivo.",
    "codigo_pt_nn": "Código do veículo fora do padrão PT-NN.",
}


def _traduzir(e: sqlite3.IntegrityError) -> RecusadoPeloBanco:
    msg = str(e)
    amigavel = next((v for k, v in MENSAGENS.items() if k in msg), "Dado recusado pelo banco.")
    return RecusadoPeloBanco(f"{amigavel} (regra do banco: {msg})")


class SqliteBase:
    def __init__(self, caminho: str | Path) -> None:
        self._caminho = str(caminho)

    def _con(self) -> sqlite3.Connection:
        return conectar(self._caminho)

    def _executar(self, sql: str, params: tuple = ()) -> int:
        con = self._con()
        try:
            with con:
                cur = con.execute(sql, params)
                return cur.rowcount
        except sqlite3.IntegrityError as e:
            raise _traduzir(e) from e
        finally:
            con.close()

    def _inserir(self, tabela: str, dados: dict) -> None:
        con = self._con()
        try:
            with con:
                inserir(con, tabela, dados)
        except sqlite3.IntegrityError as e:
            raise _traduzir(e) from e
        finally:
            con.close()

    def _um(self, sql, params=()):
        con = self._con()
        try:
            return con.execute(sql, params).fetchone()
        finally:
            con.close()

    def _df(self, sql, params=()) -> pd.DataFrame:
        con = self._con()
        try:
            return pd.read_sql(sql, con, params=params)
        finally:
            con.close()

    def _chassi(self, codigo: str) -> str | None:
        r = self._um("SELECT chassi FROM veiculo WHERE codigo = ?", (codigo,))
        return r[0] if r else None

    # ───────── porta BaseOperacional ─────────
    def existe_veiculo(self, codigo):
        return self._chassi(codigo) is not None

    def ultima_leitura(self, codigo, ate):
        r = self._um("""SELECT l.data, l.km, l.responsavel FROM leitura_km l JOIN veiculo v USING (chassi)
                        WHERE v.codigo = ? AND l.data <= ? ORDER BY l.data DESC LIMIT 1""", (codigo, ate.isoformat()))
        return LeituraKm(codigo, date.fromisoformat(r[0]), r[0], r[1], r[2], None, 0) if r else None

    def leitura_vizinha(self, codigo, data, depois):
        op, ordem = (">", "ASC") if depois else ("<", "DESC")
        r = self._um(f"""SELECT l.data, l.km, l.responsavel FROM leitura_km l JOIN veiculo v USING (chassi)
                         WHERE v.codigo = ? AND l.data {op} ? ORDER BY l.data {ordem} LIMIT 1""",
                     (codigo, data.isoformat()))
        return LeituraKm(codigo, date.fromisoformat(r[0]), r[0], r[1], r[2], None, 0) if r else None

    def substituir_leitura(self, l: LeituraKm):
        n = self._executar("""UPDATE leitura_km SET km = ?, responsavel = ?, origem = 'plataforma',
                                     lancado_em = datetime('now', 'localtime')
                              WHERE data = ? AND chassi = (SELECT chassi FROM veiculo WHERE codigo = ?)""",
                           (l.km, l.responsavel, l.data.isoformat(), l.veiculo))
        if n == 0:
            raise RecusadoPeloBanco(f"Não há leitura de {l.veiculo} em {l.data:%d/%m/%Y} para substituir.")

    def leitura_do_dia(self, codigo: str, data: date):
        r = self._um("""SELECT l.km, l.responsavel FROM leitura_km l JOIN veiculo v USING (chassi)
                        WHERE v.codigo = ? AND l.data = ?""", (codigo, data.isoformat()))
        return r

    def inserir_leitura(self, l: LeituraKm):
        self._inserir("leitura_km", {"chassi": self._chassi(l.veiculo), "data": l.data.isoformat(), "km": l.km,
                                     "responsavel": l.responsavel, "origem": "plataforma"})

    def ocorrencias_abertas(self):
        con = self._con()
        try:
            rows = con.execute("""SELECT o.ocorrencia_id, v.codigo, o.descricao, o.status, o.abertura, o.responsavel,
                                         o.grupo_duplicata
                                  FROM ocorrencia o JOIN veiculo v USING (chassi) WHERE o.status <> 'Fechado'""").fetchall()
        finally:
            con.close()
        return [Ocorrencia(i, v, d, s, date.fromisoformat(a), None, r, 0, g) for i, v, d, s, a, r, g in rows]

    def proximo_id_ocorrencia(self):
        r = self._um("""SELECT MAX(CAST(substr(ocorrencia_id, 4, 4) AS INTEGER)) FROM ocorrencia
                        WHERE ocorrencia_id GLOB 'OC-[0-9][0-9][0-9][0-9]*'""")
        return f"OC-{(r[0] or 0) + 1:04d}"

    def inserir_ocorrencia(self, o: Ocorrencia):
        self._inserir("ocorrencia", {"ocorrencia_id": o.id, "chassi": self._chassi(o.veiculo), "descricao": o.descricao,
                                     "status": o.status, "abertura": o.abertura.isoformat(), "fechamento": None,
                                     "responsavel": o.responsavel, "grupo_duplicata": o.grupo, "origem": "plataforma"})

    def fechar_ocorrencia(self, ocorrencia_id, data):
        n = self._executar("UPDATE ocorrencia SET status = 'Fechado', fechamento = ? WHERE ocorrencia_id = ?",
                           (data.isoformat(), ocorrencia_id))
        if n == 0:
            raise RecusadoPeloBanco(f"Ocorrência {ocorrencia_id} não encontrada.")

    def registrar_status_frota(self, codigo, data, status, motivo, previsao):
        self._inserir("status_frota", {"chassi": self._chassi(codigo), "data": data.isoformat(), "status": status,
                                       "motivo": motivo, "previsao_retorno": previsao.isoformat() if previsao else None})

    def registrar_teste_realizado(self, teste_id, data):
        n = self._executar("UPDATE teste SET realizada = ? WHERE teste_id = ?", (data.isoformat(), teste_id))
        if n == 0:
            raise RecusadoPeloBanco(f"Teste {teste_id} não encontrado.")

    def resolver_pendencia(self, pendencia_id):
        self._executar("UPDATE pendencia SET resolvida = 1 WHERE id = ?", (pendencia_id,))

    def reenviar_pendencia(self, pendencia_id: int, dados: dict) -> None:
        """Reenvia uma linha recusada, já corrigida pelo dono. O banco valida de novo."""
        tabela = self._um("SELECT tabela FROM pendencia WHERE id = ?", (pendencia_id,))[0]
        self._inserir(tabela, dados)
        self.resolver_pendencia(pendencia_id)

    def renomear_ocorrencia(self, antigo: str, novo: str, pendencia_id: int | None = None) -> None:
        """Troca um ID provisório pelo definitivo (o grupo de duplicata acompanha)."""
        con = self._con()
        try:
            with con:
                if con.execute("SELECT 1 FROM ocorrencia WHERE ocorrencia_id = ?", (novo,)).fetchone():
                    raise RecusadoPeloBanco(f"O ID {novo} já existe.")
                con.execute("UPDATE ocorrencia SET ocorrencia_id = ? WHERE ocorrencia_id = ?", (novo, antigo))
                con.execute("UPDATE ocorrencia SET grupo_duplicata = ? WHERE grupo_duplicata = ?", (novo, antigo))
                if pendencia_id is not None:
                    con.execute("UPDATE pendencia SET resolvida = 1 WHERE id = ?", (pendencia_id,))
        except sqlite3.IntegrityError as e:
            raise _traduzir(e) from e
        finally:
            con.close()

    # ───────── consultas (lado de leitura) ─────────
    def veiculos(self) -> pd.DataFrame:
        return self._df("SELECT codigo, chassi, programa_id AS programa FROM veiculo ORDER BY codigo")

    def pessoas(self) -> list[str]:
        df = self._df("""SELECT responsavel AS p FROM leitura_km UNION SELECT engenheiro FROM teste
                         UNION SELECT responsavel FROM ocorrencia UNION SELECT responsavel FROM pendencia""")
        return sorted(p for p in df["p"].dropna().unique())

    def pendencias(self, responsavel: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM pendencia WHERE resolvida = 0"
        df = self._df(sql + (" AND responsavel = ?" if responsavel else "") + " ORDER BY id",
                      (responsavel,) if responsavel else ())
        df["dados"] = df["dados"].map(lambda s: json.loads(s) if s else {})
        return df

    def ocorrencias(self, so_abertas: bool = True) -> pd.DataFrame:
        return self._df(f"""SELECT o.ocorrencia_id, v.codigo AS veiculo, o.descricao, o.status, o.abertura,
                                   o.fechamento, o.responsavel, o.origem
                            FROM ocorrencia o JOIN veiculo v USING (chassi)
                            {"WHERE o.status <> 'Fechado'" if so_abertas else ""} ORDER BY o.ocorrencia_id""")

    def testes_pendentes(self) -> pd.DataFrame:
        return self._df("""SELECT t.teste_id, v.codigo AS veiculo, t.tipo, t.prevista, t.status, t.engenheiro
                           FROM vw_teste t JOIN veiculo v USING (chassi) WHERE t.realizada IS NULL ORDER BY t.prevista""")

    def gate(self) -> pd.DataFrame:
        return self._df("SELECT * FROM vw_gate_programa")

    def data_referencia(self) -> date:
        return date.fromisoformat(self._um("SELECT valor FROM parametro WHERE nome = 'data_corte'")[0])

    def definir_data_referencia(self, d: date) -> None:
        self._executar("UPDATE parametro SET valor = ? WHERE nome = 'data_corte'", (d.isoformat(),))

    def km_em_dia(self, dias: int) -> pd.DataFrame:
        ref = self.data_referencia()
        df = self._df("""SELECT v.codigo AS veiculo, v.programa_id AS programa, MAX(l.data) AS ultima_leitura
                         FROM veiculo v LEFT JOIN leitura_km l USING (chassi) GROUP BY v.codigo ORDER BY v.codigo""")
        df["dias_sem_leitura"] = df["ultima_leitura"].map(lambda d: (ref - date.fromisoformat(d)).days if d else None)
        df["em_dia"] = df["dias_sem_leitura"].map(lambda n: n is not None and n <= dias)
        return df

    def ultimos_lancamentos(self) -> pd.DataFrame:
        return self._df("""SELECT lancado_em, 'Km' AS tipo, v.codigo AS veiculo,
                                  printf('%.0f km em %s', km, data) AS detalhe, responsavel
                           FROM leitura_km JOIN veiculo v USING (chassi) WHERE origem = 'plataforma'
                           UNION ALL
                           SELECT lancado_em, 'Ocorrência', v.codigo, ocorrencia_id || ' · ' || descricao, responsavel
                           FROM ocorrencia JOIN veiculo v USING (chassi) WHERE origem = 'plataforma'
                           ORDER BY 1 DESC LIMIT 15""")
