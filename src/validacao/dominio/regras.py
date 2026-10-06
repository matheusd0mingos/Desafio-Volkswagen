"""Regras de qualidade. Cada regra = uma classe pequena (SRP).
Regra nova = classe nova na lista (OCP). Todas devolvem Achados, nunca gravam nada."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Generic, Optional, Protocol, TypeVar

from .modelos import Achado, Config, LeituraKm, Ocorrencia, Origem, Severidade, Teste, Veiculo

E = TypeVar("E", contravariant=True)


@dataclass(frozen=True)
class ContextoValidacao:
    """Fatos de referência que as regras consultam (somente leitura)."""
    config: Config
    cadastro: frozenset[str] = frozenset()
    programa_por_veiculo: dict[str, str] = field(default_factory=dict)
    corte: Optional[date] = None


class Regra(Protocol, Generic[E]):
    def avaliar(self, entidade: E, ctx: ContextoValidacao, aba: str) -> list[Achado]: ...


# ───────────── Regras de entidade isolada ─────────────
class VeiculoOrfaoRule:
    def avaliar(self, e, ctx, aba):
        if e.veiculo in ctx.cadastro:
            return []
        return [Achado(Origem(aba, e.linha), "Veículo", e.veiculo, "Veículo não existe na Frota (órfão)",
                       Severidade.ALTA, "Quarentena")]


class IndisponivelSemMotivoRule:
    def avaliar(self, v: Veiculo, ctx, aba):
        if v.status == "Disponível":
            return []
        return [Achado(Origem(aba, v.linha), "Status", v.status_original,
                       "Veículo indisponível sem motivo/previsão de retorno", Severidade.MEDIA,
                       "Criar campos Motivo e Previsão")]


class FechamentoAntesAberturaRule:
    def avaliar(self, o: Ocorrencia, ctx, aba):
        if o.fechamento and o.abertura and o.fechamento < o.abertura:
            return [Achado(Origem(aba, o.linha), "Data de fechamento", f"{o.fechamento:%Y-%m-%d}",
                           "Fechamento antes da abertura", Severidade.ALTA, "Dono corrige datas")]
        return []


class FechadaSemDataRule:
    def avaliar(self, o: Ocorrencia, ctx, aba):
        if o.status == "Fechado" and o.fechamento is None:
            return [Achado(Origem(aba, o.linha), "Data de fechamento", "vazio", "Fechada sem data",
                           Severidade.MEDIA, "Dono informa")]
        return []


class StatusTesteRule:
    def avaliar(self, t: Teste, ctx, aba):
        o = Origem(aba, t.linha)
        if t.status_digitado == "Concluído" and t.realizada is None:
            return [Achado(o, "Data realizada", "vazio", "Concluído sem data realizada", Severidade.ALTA, "Dono informa data")]
        if t.status_digitado != t.status_calculado:
            return [Achado(o, "Status", t.status_original, f"Status digitado diverge das datas → {t.status_calculado}",
                           Severidade.MEDIA, "Status passa a ser calculado")]
        return []


class ProgramaDivergenteRule:
    def avaliar(self, t: Teste, ctx, aba):
        prog = ctx.programa_por_veiculo.get(t.veiculo)
        if prog is not None and prog != t.programa:
            return [Achado(Origem(aba, t.linha), "Programa", t.programa, "Programa diverge da Frota",
                           Severidade.MEDIA, "Usar Frota")]
        return []


# ───────────── Regras de par de leituras de km (Strategy) ─────────────
@dataclass(frozen=True)
class Violacao:
    campo: str
    regra: str
    acao: str
    sugestao: Optional[float] = None


class RegraLeitura(Protocol):
    def avaliar(self, atual: LeituraKm, anterior: LeituraKm, cfg: Config) -> Optional[Violacao]: ...


def _km(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _semanas(atual: LeituraKm, anterior: LeituraKm) -> float:
    return max((atual.data - anterior.data).days / 7, 1)


class MesmaDataRule:
    def avaliar(self, atual, anterior, cfg):
        if atual.data == anterior.data:
            return Violacao("Data", "Duas leituras na mesma data", "Dono escolhe a válida")
        return None


class UnidadeErradaRule:
    def avaliar(self, atual, anterior, cfg):
        if atual.km / anterior.km < 0.01:
            sug = atual.km * 1000
            return Violacao("Km acumulado", "Km em unidade errada (mil km?)", f"Sugerido {_km(sug)} — dono confirma", sug)
        return None


class RegressaoRule:
    def avaliar(self, atual, anterior, cfg):
        if atual.km < anterior.km:
            return Violacao("Km acumulado", f"Km regrediu ({_km(anterior.km)} → {_km(atual.km)})",
                            "Hodômetro ou digitação? Dono confirma")
        return None


class SaltoRule:
    def avaliar(self, atual, anterior, cfg):
        semanas = _semanas(atual, anterior)
        delta = atual.km - anterior.km
        if delta <= cfg.max_km_semana * semanas:
            return None
        sug = atual.km / 10 if atual.km / anterior.km > 5 else None
        acao = f"Provável zero a mais → sugerido {_km(sug)}" if sug else "Dono confirma"
        return Violacao("Km acumulado", f"Salto de {_km(delta)} km em {semanas:.0f} semana(s)", acao, sug)


REGRAS_LEITURA_PADRAO: tuple[RegraLeitura, ...] = (MesmaDataRule(), UnidadeErradaRule(), RegressaoRule(), SaltoRule())
