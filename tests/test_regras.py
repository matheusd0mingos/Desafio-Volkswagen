from datetime import date

from validacao.dominio.modelos import Config, LeituraKm, Ocorrencia, Qualidade
from validacao.dominio.regras import (ContextoValidacao, FechamentoAntesAberturaRule, MesmaDataRule, RegressaoRule,
                                      SaltoRule, UnidadeErradaRule, VeiculoOrfaoRule)
from validacao.dominio.servicos import ValidadorLeituras, km_rodado, status_calculado

CFG = Config()


def leitura(dia, km, veiculo="PT-01", linha=2):
    return LeituraKm(veiculo, date(2026, 3, dia), None, km, "X", None, linha)


def test_salto_com_zero_a_mais_sugere_divisao():
    v = SaltoRule().avaliar(leitura(17, 208900), leitura(10, 20870), CFG)
    assert v and v.sugestao == 20890


def test_salto_considera_intervalo_entre_leituras():
    # 3.450 km em 2 semanas é plausível (bug real da 1ª versão: PT-07)
    assert SaltoRule().avaliar(leitura(17, 21900), leitura(3, 18450), CFG) is None


def test_unidade_errada():
    assert UnidadeErradaRule().avaliar(leitura(17, 16.62), leitura(10, 16010), CFG).sugestao == 16620


def test_regressao_e_mesma_data():
    assert RegressaoRule().avaliar(leitura(10, 18120), leitura(3, 18450), CFG)
    assert MesmaDataRule().avaliar(leitura(9, 8940), leitura(9, 8760), CFG)


def test_validador_quarentena_e_continua_da_ultima_leitura_boa():
    serie = [leitura(3, 18450, linha=2), leitura(10, 18120, linha=3), leitura(17, 21900, linha=4)]
    ValidadorLeituras().validar(serie, ContextoValidacao(CFG, frozenset({"PT-01"}), corte=date(2026, 3, 17)))
    assert [l.qualidade for l in serie] == [Qualidade.OK, Qualidade.QUARENTENA, Qualidade.OK]
    assert km_rodado(serie) == 21900 - 18450


def test_orfao():
    ctx = ContextoValidacao(CFG, frozenset({"PT-01"}))
    assert VeiculoOrfaoRule().avaliar(leitura(3, 1, veiculo="PT-15"), ctx, "Km")


def test_fechamento_antes_da_abertura():
    o = Ocorrencia("OC-0107", "PT-08", "x", "Fechado", date(2026, 3, 7), date(2026, 3, 3), None, 9)
    assert FechamentoAntesAberturaRule().avaliar(o, ContextoValidacao(CFG), "Oc")


def test_status_calculado_pelas_datas():
    corte = date(2026, 3, 31)
    assert status_calculado(date(2026, 3, 9), None, "Planejado", corte) == "Atrasado"
    assert status_calculado(date(2026, 3, 9), date(2026, 3, 9), "Planejado", corte) == "Concluído"
