"""O banco como última linha de defesa: cada CONSTRAINT barra um problema do diagnóstico."""
import sqlite3

import pytest

from validacao.adaptadores.sqlite.repositorio import conectar


@pytest.fixture
def con():
    c = conectar(criar=True)
    c.execute("INSERT INTO parametro VALUES ('data_corte', '2026-03-31')")
    c.execute("INSERT INTO programa VALUES ('Alfa', 'Caminhão leve')")
    c.execute("INSERT INTO veiculo VALUES ('CHS-0001', 'PT-01', 'Alfa')")
    c.execute("INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES ('CHS-0001', '2026-03-16', 13640, 'Ana Lima')")
    yield c
    c.close()


def km(con, data="2026-03-23", valor=14000, chassi="CHS-0001"):
    con.execute("INSERT INTO leitura_km (chassi, data, km, responsavel) VALUES (?, ?, ?, 'Ana Lima')", (chassi, data, valor))


def test_leitura_valida_entra(con):
    km(con)
    assert con.execute("SELECT COUNT(*) FROM leitura_km").fetchone()[0] == 2


@pytest.mark.parametrize("kwargs, erro", [
    ({"chassi": "CHS-0015"}, "FOREIGN KEY"),          # veículo órfão
    ({"data": "16/03/2026"}, "data_iso"),              # data como texto
    ({"valor": "13.640 km"}, "km_numerico_positivo"),  # km como texto
    ({"valor": -5}, "km_numerico_positivo"),
    ({"data": "2026-03-18"}, "UNIQUE.*semana"),        # 2 leituras na mesma semana
])
def test_leitura_invalida_e_recusada(con, kwargs, erro):
    with pytest.raises(sqlite3.IntegrityError, match=erro):
        km(con, **kwargs)


def test_codigo_fora_do_padrao(con):
    with pytest.raises(sqlite3.IntegrityError, match="codigo_pt_nn"):
        con.execute("INSERT INTO veiculo VALUES ('CHS-0099', 'PT 07', 'Alfa')")


@pytest.mark.parametrize("status, abertura, fechamento, erro", [
    ("?", "2026-03-12", None, "status_ocorrencia_lista"),
    ("Fechado", "2026-03-07", "2026-03-03", "fechamento_apos_abertura"),
    ("Fechado", "2026-03-07", None, "fechado_tem_data"),
])
def test_ocorrencia_invalida(con, status, abertura, fechamento, erro):
    with pytest.raises(sqlite3.IntegrityError, match=erro):
        con.execute("INSERT INTO ocorrencia (ocorrencia_id, chassi, descricao, status, abertura, fechamento, "
                    "responsavel, grupo_duplicata) VALUES ('OC-0001','CHS-0001','x',?,?,?,'Ana','OC-0001')",
                    (status, abertura, fechamento))


def test_indisponivel_exige_motivo(con):
    with pytest.raises(sqlite3.IntegrityError, match="indisponivel_exige_motivo"):
        con.execute("INSERT INTO status_frota (chassi, data, status) VALUES ('CHS-0001', '2026-03-09', 'Em manutenção')")


def test_status_do_teste_e_calculado(con):
    con.execute("INSERT INTO teste VALUES ('T-003','CHS-0001','Frenagem','2026-03-09',NULL,0,'Ana')")
    assert con.execute("SELECT status FROM vw_teste").fetchone()[0] == "Atrasado"
