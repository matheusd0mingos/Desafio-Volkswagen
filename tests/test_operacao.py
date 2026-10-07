"""Operação do dia a dia: o dado entra uma vez, já validado (domínio + banco)."""
from datetime import date
from pathlib import Path
import os

import pytest

from validacao.adaptadores.sqlite.base_operacional import SqliteBase
from validacao.adaptadores.sqlite.bootstrap import garantir_base
from validacao.adaptadores.sqlite.repositorio import conectar
from validacao.aplicacao.portas import RecusadoPeloBanco
from validacao.aplicacao.operacao import (AbrirOcorrencia, AtualizarStatusFrota, FecharOcorrencia,
                                          LancarLeituraKm, RegistrarTesteRealizado)


@pytest.fixture
def base(tmp_path):
    db = tmp_path / "op.db"
    con = conectar(db, criar=True)
    con.executescript("""
        INSERT INTO parametro VALUES ('data_corte', '2026-03-31');
        INSERT INTO programa VALUES ('Alfa', 'Caminhão leve');
        INSERT INTO veiculo VALUES ('CHS-0001', 'PT-01', 'Alfa');
        INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-16', 13640, 'Ana Lima');
        INSERT INTO teste VALUES ('T-003', 'CHS-0001', 'Frenagem', '2026-03-09', NULL, 0, 'Ana Lima');
        INSERT INTO ocorrencia (ocorrencia_id, chassi, descricao, status, abertura, responsavel, grupo_duplicata)
            VALUES ('OC-0116', 'CHS-0001', 'Folga na direção', 'Aberto', '2026-03-14', 'Ana Lima', 'OC-0116');""")
    con.commit(); con.close()
    return SqliteBase(db)


def test_leitura_valida_entra_e_muda_o_gate(base):
    antes = base.gate()["km_rodado"].sum()
    r = LancarLeituraKm(base).executar("PT-01", date(2026, 3, 23), 14300, "Ana Lima")
    assert r.aceito
    assert base.gate()["km_rodado"].sum() == antes + 660


def test_veiculo_fora_do_cadastro(base):
    assert not LancarLeituraKm(base).executar("PT-15", date(2026, 3, 23), 900, "Ana Lima").aceito


def test_regressao_e_recusada_sem_opcao_de_confirmar(base):
    r = LancarLeituraKm(base).executar("PT-01", date(2026, 3, 23), 13000, "Ana Lima")
    assert not r.aceito and not r.pede_confirmacao and "regrediu" in r.mensagem


def test_salto_pede_confirmacao_e_aceita_quando_confirmado(base):
    caso = LancarLeituraKm(base)
    r = caso.executar("PT-01", date(2026, 3, 23), 136400, "Ana Lima")
    assert not r.aceito and r.pede_confirmacao
    assert caso.executar("PT-01", date(2026, 3, 23), 136400, "Ana Lima", confirmado=True).aceito


def test_mesma_semana_barrada_pelo_banco_com_mensagem_amigavel(base):
    r = LancarLeituraKm(base).executar("PT-01", date(2026, 3, 18), 13900, "Ana Lima")
    assert not r.aceito and "nesta semana" in r.mensagem


def test_ocorrencia_duplicada_pede_confirmacao(base):
    caso = AbrirOcorrencia(base)
    r = caso.executar("PT-01", "Folga na direção", date(2026, 3, 20), "Ana Lima")
    assert r.pede_confirmacao and "OC-0116" in r.mensagem
    r = caso.executar("PT-01", "Folga na direção ao frear", date(2026, 3, 20), "Ana Lima", confirmado=True)
    assert r.aceito and "OC-0117" in r.mensagem


def test_fechar_antes_da_abertura_e_recusado(base):
    assert not FecharOcorrencia(base).executar("OC-0116", date(2026, 3, 1)).aceito
    assert FecharOcorrencia(base).executar("OC-0116", date(2026, 3, 20)).aceito
    assert base.gate()["falhas_abertas"].sum() == 0


def test_indisponivel_exige_motivo(base):
    caso = AtualizarStatusFrota(base)
    assert not caso.executar("PT-01", date(2026, 3, 20), "Em manutenção", "", None).aceito
    assert caso.executar("PT-01", date(2026, 3, 20), "Em manutenção", "Troca de embreagem", date(2026, 3, 27)).aceito


def test_teste_realizado_muda_status_calculado(base):
    assert RegistrarTesteRealizado(base).executar("T-003", date(2026, 3, 20)).aceito
    assert base.gate()["testes_concluidos"].sum() == 1


ARQUIVO = Path(os.environ.get("CASE_XLSX", Path(__file__).parents[1] / "Case_Dados_Validacao_.xlsx"))


@pytest.mark.integracao
@pytest.mark.skipif(not ARQUIVO.is_file(), reason="coloque o Excel do case na raiz do projeto")
def test_carga_inicial_e_resolucao_de_pendencia(tmp_path):
    db = tmp_path / "v.db"
    assert garantir_base(db, ARQUIVO.read_bytes()) is True
    assert garantir_base(db, ARQUIVO.read_bytes()) is False          # Excel só na primeira vez
    base = SqliteBase(db)
    p = base.pendencias("Patrícia Rocha")
    pt04 = p[(p["tabela"] == "leitura_km") & (p["chave"] == "PT-04")].iloc[0]
    assert pt04["valor_sugerido"] == 20890
    r = LancarLeituraKm(base).executar("PT-04", date(2026, 3, 17), pt04["valor_sugerido"], "Patrícia Rocha",
                                       pendencia_id=int(pt04["id"]))
    assert r.aceito
    assert pt04["id"] not in base.pendencias("Patrícia Rocha")["id"].values


@pytest.mark.integracao
@pytest.mark.skipif(not ARQUIVO.is_file(), reason="coloque o Excel do case na raiz do projeto")
def test_dono_corrige_status_e_reenvia(tmp_path):
    db = tmp_path / "v.db"
    garantir_base(db, ARQUIVO.read_bytes())
    base = SqliteBase(db)
    antes = base.gate()["falhas_abertas"].sum()
    p = base.pendencias("Ana Lima")
    oc = p[p["chave"] == "OC-0112"].iloc[0]
    dados = dict(oc["dados"], status="Indefinido")
    with pytest.raises(RecusadoPeloBanco):
        base.reenviar_pendencia(int(oc["id"]), dados)                 # continua inválido
    base.reenviar_pendencia(int(oc["id"]), dict(dados, status="Em análise"))
    assert base.gate()["falhas_abertas"].sum() == antes + 1           # 10 → 11: o "?" virou falha confirmada


def test_duas_leituras_no_mesmo_dia_dono_escolhe(base):
    from validacao.aplicacao.operacao import SubstituirLeituraKm
    assert LancarLeituraKm(base).executar("PT-01", date(2026, 3, 23), 14300, "Ana Lima").aceito
    caso = SubstituirLeituraKm(base)
    r = caso.executar("PT-01", date(2026, 3, 16), 15000, "Ana Lima")
    assert not r.aceito and "seguinte" in r.mensagem                       # passaria da leitura de 23/03
    assert caso.executar("PT-01", date(2026, 3, 16), 13700, "Ana Lima").aceito
    assert base.leitura_do_dia("PT-01", date(2026, 3, 16))[0] == 13700
