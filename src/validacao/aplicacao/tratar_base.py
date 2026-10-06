"""Caso de uso: tratar a base bruta. Só orquestra domínio + portas."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from typing import Sequence

from ..dominio import catalogos as cat
from ..dominio.modelos import Achado, Config, LeituraKm, Ocorrencia, Origem, Teste, Veiculo
from ..dominio.normalizadores import (CatalogoNormalizador, DataNormalizador, Normalizador,
                                      OcorrenciaIDNormalizador, PessoaNormalizador, StatusNormalizador,
                                      VeiculoIDNormalizador)
from ..dominio.regras import (ContextoValidacao, FechadaSemDataRule, FechamentoAntesAberturaRule,
                              IndisponivelSemMotivoRule, ProgramaDivergenteRule, Regra, StatusTesteRule,
                              VeiculoOrfaoRule)
from ..dominio.servicos import AnalisadorOcorrencias, ValidadorLeituras, km_rodado, status_calculado
from ..dominio.texto import vazio
from .portas import FonteDadosBrutos, LinhaBruta, RepositorioResultado, ResultadoTratamento, Resumo


class _Coletor:
    """Aplica normalizadores acumulando achados (evita repetir boilerplate)."""

    def __init__(self) -> None:
        self.achados: list[Achado] = []

    def __call__(self, normalizador: Normalizador, valor, origem: Origem, campo: str):
        r = normalizador.normalizar(valor, origem, campo)
        self.achados.extend(r.achados)
        return r.valor


class TratarBaseDeValidacao:
    def __init__(self, fonte: FonteDadosBrutos, repositorio: RepositorioResultado,
                 config: Config = Config(),
                 validador_leituras: ValidadorLeituras | None = None,
                 analisador: AnalisadorOcorrencias | None = None,
                 regras_frota: Sequence[Regra] = (IndisponivelSemMotivoRule(),),
                 regras_ocorrencia: Sequence[Regra] = (VeiculoOrfaoRule(), FechamentoAntesAberturaRule(), FechadaSemDataRule()),
                 regras_teste: Sequence[Regra] = (VeiculoOrfaoRule(), StatusTesteRule(), ProgramaDivergenteRule())) -> None:
        self._fonte, self._repo, self._cfg = fonte, repositorio, config
        self._validador = validador_leituras or ValidadorLeituras()
        self._analisador = analisador or AnalisadorOcorrencias()
        self._regras_frota, self._regras_oc, self._regras_teste = regras_frota, regras_ocorrencia, regras_teste
        self._veiculo, self._data = VeiculoIDNormalizador(), DataNormalizador()

    # ───────── fluxo principal ─────────
    def executar(self) -> ResultadoTratamento:
        bruto = self._fonte.ler()
        col = _Coletor()
        pessoa = PessoaNormalizador(sorted({r["Engenheiro"] for r in bruto.plano_testes}))

        veiculos = self._veiculos(bruto.frota, col)
        leituras = self._leituras(bruto.quilometragem, col, pessoa)
        ctx = ContextoValidacao(self._cfg, frozenset(v.id for v in veiculos),
                                {v.id: v.programa for v in veiculos},
                                corte=max(l.data for l in leituras if l.data))
        ocorrencias = self._ocorrencias(bruto.ocorrencias, col, pessoa)
        testes = self._testes(bruto.plano_testes, col, ctx)

        achados = col.achados
        achados += self._aplicar(self._regras_frota, veiculos, ctx, "Frota")
        achados += self._validador.validar(leituras, ctx)
        achados += self._aplicar(self._regras_oc, ocorrencias, ctx, "Ocorrencias")
        achados += self._analisador.agrupar_duplicatas(ocorrencias, self._cfg)
        achados += self._analisador.falhas_sistemicas(ocorrencias, self._cfg)
        achados += self._aplicar(self._regras_teste, testes, ctx, "Plano_Testes")

        resumo = Resumo(
            falhas_abertas_antes=_contagens_ingenuas(bruto.ocorrencias),
            falhas_abertas_depois=AnalisadorOcorrencias.abertas_unicas(ocorrencias, ctx.cadastro),
            km_rodado_bruto=_km_rodado_bruto(bruto.quilometragem),
            km_rodado_tratado=km_rodado(leituras),
            total_achados=len(achados),
            corte=ctx.corte)
        resultado = ResultadoTratamento(veiculos, leituras, ocorrencias, testes, achados, resumo)
        self._repo.salvar(resultado)
        return resultado

    @staticmethod
    def _aplicar(regras, entidades, ctx, aba) -> list[Achado]:
        return [a for e in entidades for r in regras for a in r.avaliar(e, ctx, aba)]

    # ───────── normalização por fonte ─────────
    def _veiculos(self, linhas: list[LinhaBruta], col: _Coletor) -> list[Veiculo]:
        status = StatusNormalizador(cat.STATUS_FROTA)
        out = []
        for n, r in enumerate(linhas, start=2):
            o = Origem("Frota", n)
            out.append(Veiculo(col(self._veiculo, r["Veículo"], o, "Veículo"), r["Chassi (fictício)"], r["Programa"],
                               r["Tipo"], col(status, r["Status"], o, "Status"), r["Status"],
                               col(self._data, r["Atualizado em"], o, "Atualizado em"), n))
        return out

    def _leituras(self, linhas, col, pessoa) -> list[LeituraKm]:
        out = []
        for n, r in enumerate(linhas, start=2):
            o = Origem("Quilometragem", n)
            out.append(LeituraKm(col(self._veiculo, r["Veículo"], o, "Veículo"),
                                 col(self._data, r["Data"], o, "Data"), r["Data"],
                                 None if vazio(r["Km acumulado"]) else float(r["Km acumulado"]),
                                 col(pessoa, r["Responsável"], o, "Responsável"), r["Observação"], n))
        return out

    def _ocorrencias(self, linhas, col, pessoa) -> list[Ocorrencia]:
        status, ids = StatusNormalizador(cat.STATUS_OCORRENCIA), OcorrenciaIDNormalizador()
        out = []
        for n, r in enumerate(linhas, start=2):
            o = Origem("Ocorrencias", n)
            fech = r["Data de fechamento"]
            out.append(Ocorrencia(col(ids, r["ID"], o, "ID"), col(self._veiculo, r["Veículo"], o, "Veículo"),
                                  r["Descrição"], col(status, r["Status"], o, "Status"),
                                  col(self._data, r["Data de abertura"], o, "Data de abertura"),
                                  None if vazio(fech) else fech.date(),
                                  col(pessoa, r["Responsável"], o, "Responsável"), n))
        return out

    def _testes(self, linhas, col, ctx) -> list[Teste]:
        status = StatusNormalizador(cat.STATUS_TESTE)
        nome = CatalogoNormalizador(cat.NOME_TESTE, "Nome de teste fora do catálogo")
        out = []
        for n, r in enumerate(linhas, start=2):
            o = Origem("Plano_Testes", n)
            prev = col(self._data, r["Data prevista"], o, "Data prevista")
            real = col(self._data, r["Data realizada"], o, "Data realizada")
            dig = col(status, r["Status"], o, "Status")
            out.append(Teste(r["ID teste"], col(self._veiculo, r["Veículo"], o, "Veículo"), r["Programa"],
                             col(nome, r["Teste"], o, "Teste"), prev, real, r["Status"], dig,
                             status_calculado(prev, real, dig, ctx.corte), r["Engenheiro"], n))
        return out


# ───────── "antes": como alguém contaria olhando a planilha crua ─────────
def _contagens_ingenuas(ocorrencias: list[LinhaBruta]) -> dict[str, int]:
    st = [str(r["Status"]) for r in ocorrencias]
    return {"Contagem literal 'Aberto'": sum(s == "Aberto" for s in st),
            "Aberto (qualquer grafia)": sum(s.lower() == "aberto" for s in st),
            "Tudo que não está fechado": sum(s.lower() not in {"fechado", "concluído", "concluido"} for s in st)}


def _km_rodado_bruto(linhas: list[LinhaBruta]) -> float:
    series: OrderedDict[str, list[float]] = OrderedDict()
    for r in linhas:
        if not vazio(r["Km acumulado"]):
            series.setdefault(r["Veículo"], []).append(r["Km acumulado"])
    return sum(s[-1] - s[0] for s in series.values())
