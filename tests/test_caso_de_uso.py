"""Testa o caso de uso inteiro SEM Excel: só adaptadores em memória."""
import os
from datetime import datetime
from pathlib import Path

import pytest

from fakes import FonteEmMemoria, RepositorioEmMemoria
from validacao.aplicacao.portas import BaseBruta
from validacao.adaptadores.excel import ExcelFonte, ExcelRepositorio
from validacao.aplicacao.tratar_base import TratarBaseDeValidacao

D = datetime


def base_minima() -> BaseBruta:
    frota = [{"Veículo": "PT-01", "Chassi (fictício)": "C1", "Programa": "Alfa", "Tipo": "Leve",
              "Status": "Disponível", "Atualizado em": D(2026, 3, 2)}]
    km = [{"Veículo": "PT-01", "Data": D(2026, 3, 2), "Km acumulado": 1000.0, "Responsável": "Ana Lima", "Observação": None},
          {"Veículo": "pt01", "Data": "09/03/2026", "Km acumulado": 1500.0, "Responsável": "A. Lima", "Observação": None}]
    oc = [{"ID": 1, "Veículo": "PT-01", "Descrição": "Trinca no suporte", "Status": "ABERTO",
           "Data de abertura": D(2026, 3, 3), "Data de fechamento": None, "Responsável": "Ana Lima"},
          {"ID": 2, "Veículo": "PT-01", "Descrição": "Trinca no suporte", "Status": "Fechado",
           "Data de abertura": D(2026, 3, 3), "Data de fechamento": D(2026, 3, 8), "Responsável": "Ana Lima"}]
    pl = [{"ID teste": "T-001", "Veículo": "PT-01", "Programa": "Alfa", "Teste": "Frenagem",
           "Data prevista": D(2026, 3, 5), "Data realizada": None, "Status": "Planejado", "Engenheiro": "Ana Lima"}]
    return BaseBruta(frota, km, oc, pl)


def test_fluxo_completo_em_memoria():
    repo = RepositorioEmMemoria()
    r = TratarBaseDeValidacao(FonteEmMemoria(base_minima()), repo).executar()
    assert repo.salvo is r                                  # porta de saída foi chamada
    assert {l.veiculo for l in r.leituras} == {"PT-01"}     # pt01 padronizado
    assert r.resumo.falhas_abertas_depois == 0              # duplicata fechada fecha o grupo
    assert r.testes[0].status_calculado == "Atrasado"
    assert r.resumo.km_rodado_tratado == 500


ARQUIVO = Path(os.environ.get("CASE_XLSX", Path(__file__).parents[1] / "Case_Dados_Validacao_.xlsx"))


@pytest.mark.integracao
@pytest.mark.skipif(not ARQUIVO.is_file(), reason="coloque o Excel do case na raiz do projeto")
def test_numeros_do_deck_com_arquivo_real(tmp_path):
    r = TratarBaseDeValidacao(ExcelFonte(str(ARQUIVO)), ExcelRepositorio(str(tmp_path / "out.xlsx"))).executar().resumo
    assert list(r.falhas_abertas_antes.values()) == [9, 11, 16]
    assert r.falhas_abertas_depois == 12
    assert round(r.km_rodado_bruto) == 183767 and r.km_rodado_tratado == 11730
    assert r.total_achados == 80


@pytest.mark.integracao
@pytest.mark.skipif(not ARQUIVO.is_file(), reason="coloque o Excel do case na raiz do projeto")
def test_sqlite_bate_com_o_dominio(tmp_path):
    import sqlite3
    from validacao.adaptadores.sqlite.repositorio import SqliteRepositorio
    TratarBaseDeValidacao(ExcelFonte(str(ARQUIVO)), SqliteRepositorio(tmp_path / "v.db")).executar()
    con = sqlite3.connect(tmp_path / "v.db")
    gate = {r[0]: r[1:] for r in con.execute("SELECT * FROM vw_gate_programa")}
    assert sum(g[1] for g in gate.values()) == 11730                 # km igual ao Python
    assert sum(g[2] for g in gate.values()) == 10                    # 12 − 2 com status '?' barrados
    assert con.execute("SELECT COUNT(*) FROM pendencia WHERE barrado_por = 'Banco'").fetchone()[0] == 8
