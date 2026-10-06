"""Serviços de domínio: lógica que envolve várias entidades."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from itertools import combinations
from typing import Iterable, Sequence

from .modelos import Achado, Config, LeituraKm, Ocorrencia, Origem, Qualidade, Severidade
from .regras import REGRAS_LEITURA_PADRAO, ContextoValidacao, RegraLeitura, VeiculoOrfaoRule
from .texto import sem_acento


class ValidadorLeituras:
    """Percorre as leituras de cada veículo em ordem; a 1ª regra que dispara põe em quarentena."""

    ABA = "Quilometragem"

    def __init__(self, regras: Sequence[RegraLeitura] = REGRAS_LEITURA_PADRAO) -> None:
        self._regras = regras
        self._orfao = VeiculoOrfaoRule()

    def validar(self, leituras: list[LeituraKm], ctx: ContextoValidacao) -> list[Achado]:
        achados: list[Achado] = []
        por_veiculo: dict[str, list[LeituraKm]] = defaultdict(list)
        for l in sorted(leituras, key=lambda l: (l.veiculo, l.data, l.linha)):
            por_veiculo[l.veiculo].append(l)
        for serie in por_veiculo.values():
            achados += self._validar_serie(serie, ctx)
        achados += self._leituras_atrasadas(leituras, ctx)
        return achados

    def _validar_serie(self, serie: list[LeituraKm], ctx: ContextoValidacao) -> list[Achado]:
        achados, anterior = [], None
        for atual in serie:
            orfao = self._orfao.avaliar(atual, ctx, self.ABA)
            if orfao:
                achados += orfao
                atual.qualidade = Qualidade.QUARENTENA
            if atual.km is None:
                achados.append(Achado(Origem(self.ABA, atual.linha), "Km acumulado", "vazio", "Km vazio",
                                      Severidade.ALTA, "Cobrar do responsável"))
                atual.qualidade = Qualidade.QUARENTENA
                continue
            if anterior is not None:
                v = next((v for r in self._regras if (v := r.avaliar(atual, anterior, ctx.config))), None)
                if v:
                    original = atual.data_original if v.campo == "Data" else atual.km
                    achados.append(Achado(Origem(self.ABA, atual.linha), v.campo, str(original), v.regra,
                                          Severidade.ALTA, v.acao))
                    atual.qualidade, atual.km_sugerido = Qualidade.QUARENTENA, v.sugestao
            if atual.qualidade is Qualidade.OK:
                anterior = atual
        return achados

    def _leituras_atrasadas(self, leituras: list[LeituraKm], ctx: ContextoValidacao) -> list[Achado]:
        cfg, corte = ctx.config, ctx.corte
        ultima: dict[str, date] = {}
        for l in leituras:
            if l.qualidade is Qualidade.OK:
                ultima[l.veiculo] = max(ultima.get(l.veiculo, l.data), l.data)
        return [Achado(Origem(self.ABA, "-"), "Veículo", vid,
                       f"Sem leitura válida há mais de {cfg.dias_sem_leitura} dias (corte {corte:%d/%m})",
                       Severidade.MEDIA, "Lembrete automático ao responsável")
                for vid in sorted(ctx.cadastro)
                if vid not in ultima or (corte - ultima[vid]).days > cfg.dias_sem_leitura]


def km_rodado(leituras: Iterable[LeituraKm]) -> float:
    """Última − primeira leitura válida por veículo, somado na frota."""
    series: dict[str, list[LeituraKm]] = defaultdict(list)
    for l in sorted(leituras, key=lambda l: (l.veiculo, l.data, l.linha)):
        if l.qualidade is Qualidade.OK:
            series[l.veiculo].append(l)
    return sum(s[-1].km - s[0].km for s in series.values())


class Similaridade:
    STOP = frozenset({"no", "na", "do", "da", "de", "em", "acima", "o", "a"})

    def palavras(self, texto: str) -> set[str]:
        return {w for w in re.findall(r"\w+", sem_acento(texto)) if w not in self.STOP}

    def __call__(self, a: str, b: str) -> float:
        pa, pb = self.palavras(a), self.palavras(b)
        return len(pa & pb) / len(pa | pb) if pa | pb else 0.0


class AnalisadorOcorrencias:
    ABA = "Ocorrencias"

    def __init__(self, similaridade: Similaridade | None = None) -> None:
        self._sim = similaridade or Similaridade()

    def agrupar_duplicatas(self, ocorrencias: list[Ocorrencia], cfg: Config) -> list[Achado]:
        achados = []
        for o in ocorrencias:
            o.grupo = o.id
        for a, b in combinations(ocorrencias, 2):
            if a.veiculo == b.veiculo and self._sim(a.descricao, b.descricao) >= cfg.limiar_duplicata:
                b.grupo = a.grupo
                achados.append(Achado(Origem(self.ABA, b.linha), "Descrição", b.descricao,
                                      f"Provável duplicata de {a.id}", Severidade.ALTA, "Dono confirma e mescla"))
        return achados

    def falhas_sistemicas(self, ocorrencias: list[Ocorrencia], cfg: Config) -> list[Achado]:
        return [Achado(Origem(self.ABA, b.linha), "Descrição", b.descricao,
                       f"Mesma falha de {a.id} ({a.veiculo}) em outro veículo",
                       Severidade.INFO, "Avaliar falha sistêmica entre programas")
                for a, b in combinations(ocorrencias, 2)
                if a.veiculo != b.veiculo and self._sim(a.descricao, b.descricao) >= cfg.limiar_sistemica]

    @staticmethod
    def abertas_unicas(ocorrencias: list[Ocorrencia], cadastro: frozenset[str]) -> int:
        fechados = {o.grupo for o in ocorrencias if o.status == "Fechado"}
        return len({o.grupo for o in ocorrencias
                    if o.status != "Fechado" and o.grupo not in fechados and o.veiculo in cadastro})


def status_calculado(prevista: date | None, realizada: date | None, digitado: str, corte: date) -> str:
    """Política: status sai das datas, não da digitação."""
    if realizada is not None:
        return "Concluído"
    if prevista is not None and prevista < corte:
        return "Atrasado"
    return digitado
