"""Adaptador SQLite (carga inicial): grava a base tratada. O banco recusa o que viola o modelo."""
from __future__ import annotations

import json
import sqlite3
from importlib import resources
from pathlib import Path

from ...aplicacao.portas import ResultadoTratamento
from ...dominio.modelos import Qualidade


VERSAO_BASE = "4"   # suba quando o esquema ou a carga mudarem: bases antigas são refeitas


def schema_sql() -> str:
    return resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


def conectar(caminho: str | Path = ":memory:", criar: bool = False) -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys = ON")
    if criar:
        con.executescript(schema_sql())
    return con


def inserir(con: sqlite3.Connection, tabela: str, dados: dict) -> None:
    cols = ", ".join(dados)
    con.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({', '.join('?' * len(dados))})", tuple(dados.values()))


def registrar_pendencia(con, tabela, linha, chave, motivo, por, responsavel=None, dados=None, sugestao=None) -> None:
    inserir(con, "pendencia", {"tabela": tabela, "linha_origem": linha, "chave": chave, "motivo": motivo,
                               "barrado_por": por, "responsavel": responsavel,
                               "dados": json.dumps(dados, ensure_ascii=False) if dados else None,
                               "valor_sugerido": sugestao})


class SqliteRepositorio:
    def __init__(self, caminho: str | Path) -> None:
        self._caminho = Path(caminho)

    def salvar(self, r: ResultadoTratamento) -> None:
        self._caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho.unlink(missing_ok=True)       # carga completa e idempotente
        con = conectar(self._caminho, criar=True)
        try:
            with con:
                self._carregar(con, r)
        finally:
            con.close()

    def _carregar(self, con: sqlite3.Connection, r: ResultadoTratamento) -> None:
        inserir(con, "parametro", {"nome": "data_corte", "valor": r.resumo.corte.isoformat()})
        inserir(con, "parametro", {"nome": "versao_base", "valor": VERSAO_BASE})
        for prog, tipo in sorted({(v.programa, v.tipo) for v in r.veiculos}):
            inserir(con, "programa", {"programa_id": prog, "tipo_veiculo": tipo})

        chassi = {v.id: v.chassi for v in r.veiculos}
        # a regra que pôs cada leitura em quarentena (para a pendência dizer o porquê)
        regra_km = {}
        for a in r.achados:
            if (a.origem.aba == "Quilometragem" and a.severidade.value == "Alta"
                    and not a.regra.startswith("Data em formato")):
                regra_km.setdefault(a.origem.linha, a.regra)
        for v in r.veiculos:
            self._tentar(con, "veiculo", v.linha, v.id, "Logística",
                         {"chassi": v.chassi, "codigo": v.id, "programa_id": v.programa})
            self._tentar(con, "status_frota", v.linha, v.id, "Logística",
                         {"chassi": v.chassi, "data": _iso(v.atualizado_em), "status": v.status})

        for l in r.leituras:
            dados = {"chassi": chassi.get(l.veiculo, l.veiculo), "data": _iso(l.data), "km": l.km,
                     "responsavel": l.responsavel, "linha_origem": l.linha}
            if l.qualidade is Qualidade.QUARENTENA:
                registrar_pendencia(con, "leitura_km", l.linha, l.veiculo, regra_km.get(l.linha, "Quarentena"),
                                    "Domínio", l.responsavel, dados, l.km_sugerido)
            else:
                self._tentar(con, "leitura_km", l.linha, l.veiculo, l.responsavel, dados)

        for t in r.testes:
            self._tentar(con, "teste", t.linha, t.id, t.engenheiro,
                         {"teste_id": t.id, "chassi": chassi.get(t.veiculo, t.veiculo), "tipo": t.nome,
                          "prevista": _iso(t.prevista), "realizada": _iso(t.realizada),
                          "iniciado": int(t.status_digitado == "Em andamento"), "engenheiro": t.engenheiro})

        for o in r.ocorrencias:
            dados = {"ocorrencia_id": o.id, "chassi": chassi.get(o.veiculo, o.veiculo), "descricao": o.descricao,
                     "status": o.status, "abertura": _iso(o.abertura), "fechamento": _iso(o.fechamento),
                     "responsavel": o.responsavel, "grupo_duplicata": o.grupo, "linha_origem": o.linha}
            if self._tentar(con, "ocorrencia", o.linha, o.id, o.responsavel, dados) and "SEMID" in o.id:
                # entrou (conta no Gate), mas o ID provisório não pode virar permanente
                registrar_pendencia(con, "ocorrencia", o.linha, o.id, "Ocorrência sem ID", "Domínio",
                                    o.responsavel, dados)

        con.executemany("INSERT INTO log_qualidade VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [(a.origem.aba, str(a.origem.linha), a.campo, a.valor_original, a.regra,
                          a.severidade.value, a.acao) for a in r.achados])

    @staticmethod
    def _tentar(con, tabela, linha, chave, responsavel, dados) -> bool:
        try:
            inserir(con, tabela, dados)
            return True
        except sqlite3.IntegrityError as e:
            registrar_pendencia(con, tabela, linha, chave, str(e), "Banco", responsavel, dados)
            return False


def _iso(d) -> str | None:
    return d.isoformat() if d else None
