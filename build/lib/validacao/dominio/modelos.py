"""Entidades e objetos de valor. Zero dependência externa (nem pandas)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class Severidade(str, Enum):
    ALTA = "Alta"
    MEDIA = "Média"
    BAIXA = "Baixa"
    INFO = "Info"


class Qualidade(str, Enum):
    OK = "OK"
    QUARENTENA = "Quarentena"


@dataclass(frozen=True)
class Origem:
    """De onde veio o dado: rastreabilidade até a linha do Excel."""
    aba: str
    linha: int | str


@dataclass(frozen=True)
class Achado:
    origem: Origem
    campo: str
    valor_original: str
    regra: str
    severidade: Severidade
    acao: str


@dataclass(frozen=True)
class Normalizado(Generic[T]):
    """Resultado de normalização: valor + achados. Sem efeito colateral."""
    valor: T
    achados: tuple[Achado, ...] = ()


@dataclass(frozen=True)
class Config:
    max_km_semana: int = 3000
    dias_sem_leitura: int = 7
    limiar_duplicata: float = 0.5
    limiar_sistemica: float = 0.6


@dataclass
class Veiculo:
    id: str
    chassi: str
    programa: str
    tipo: str
    status: str
    status_original: str
    atualizado_em: Optional[date]
    linha: int


@dataclass
class LeituraKm:
    veiculo: str
    data: Optional[date]
    data_original: object
    km: Optional[float]
    responsavel: Optional[str]
    observacao: Optional[str]
    linha: int
    qualidade: Qualidade = Qualidade.OK
    km_sugerido: Optional[float] = None


@dataclass
class Ocorrencia:
    id: str
    veiculo: str
    descricao: str
    status: str
    abertura: Optional[date]
    fechamento: Optional[date]
    responsavel: Optional[str]
    linha: int
    grupo: str = ""


@dataclass
class Teste:
    id: str
    veiculo: str
    programa: str
    nome: str
    prevista: Optional[date]
    realizada: Optional[date]
    status_original: str
    status_digitado: str
    status_calculado: str
    engenheiro: str
    linha: int
