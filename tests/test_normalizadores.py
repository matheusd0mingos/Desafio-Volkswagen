from datetime import date, datetime

import pytest

from validacao.dominio.modelos import Origem, Severidade
from validacao.dominio.normalizadores import (DataNormalizador, OcorrenciaIDNormalizador, PessoaNormalizador,
                                              StatusNormalizador, VeiculoIDNormalizador)
from validacao.dominio.catalogos import STATUS_OCORRENCIA

O = Origem("Aba", 2)


@pytest.mark.parametrize("bruto", ["PT 07", "pt07", "Protótipo 7", "PT-7"])
def test_veiculo_variantes_viram_padrao(bruto):
    r = VeiculoIDNormalizador().normalizar(bruto, O)
    assert r.valor == "PT-07" and len(r.achados) == 1


def test_veiculo_ja_padrao_nao_gera_achado():
    assert VeiculoIDNormalizador().normalizar("PT-07", O).achados == ()


@pytest.mark.parametrize("bruto, esperado, sev", [
    ("09/03/2026", date(2026, 3, 9), Severidade.BAIXA),
    ("03/18/2026", date(2026, 3, 18), Severidade.ALTA),   # americano
    ("2026-03-10", date(2026, 3, 10), Severidade.BAIXA),
])
def test_data_texto(bruto, esperado, sev):
    r = DataNormalizador().normalizar(bruto, O, "Data")
    assert r.valor == esperado and r.achados[0].severidade is sev


def test_data_nativa_passa_limpa():
    r = DataNormalizador().normalizar(datetime(2026, 3, 2), O, "Data")
    assert r.valor == date(2026, 3, 2) and r.achados == ()


@pytest.mark.parametrize("bruto, esperado", [("ABERTO", "Aberto"), ("Em Analise", "Em análise"),
                                             ("Concluído", "Fechado"), ("?", "Indefinido")])
def test_status_ocorrencia(bruto, esperado):
    assert StatusNormalizador(STATUS_OCORRENCIA).normalizar(bruto, O).valor == esperado


@pytest.mark.parametrize("bruto", ["marcos s.", "M. Silva", "Marcos Silva"])
def test_pessoa_abreviada(bruto):
    assert PessoaNormalizador(["Ana Lima", "Marcos Silva"]).normalizar(bruto, O).valor == "Marcos Silva"


def test_id_ocorrencia_duplicado_e_vazio():
    n = OcorrenciaIDNormalizador()
    assert n.normalizar(106, O).valor == "OC-0106"
    assert n.normalizar(106, O).valor == "OC-0106-B"
    assert n.normalizar(None, Origem("Aba", 15)).valor == "OC-SEMID-15"
    assert n.normalizar("OC-117", O).valor == "OC-0117"
