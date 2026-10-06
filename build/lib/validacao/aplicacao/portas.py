"""Portas (hexagonal): o que a aplicação PRECISA do mundo, sem saber quem fornece."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..dominio.modelos import Achado, LeituraKm, Ocorrencia, Teste, Veiculo

LinhaBruta = dict[str, Any]


@dataclass(frozen=True)
class BaseBruta:
    frota: list[LinhaBruta]
    quilometragem: list[LinhaBruta]
    ocorrencias: list[LinhaBruta]
    plano_testes: list[LinhaBruta]


@dataclass(frozen=True)
class Resumo:
    falhas_abertas_antes: dict[str, int]
    falhas_abertas_depois: int
    km_rodado_bruto: float
    km_rodado_tratado: float
    total_achados: int
    corte: Any


@dataclass(frozen=True)
class ResultadoTratamento:
    veiculos: list[Veiculo]
    leituras: list[LeituraKm]
    ocorrencias: list[Ocorrencia]
    testes: list[Teste]
    achados: list[Achado]
    resumo: Resumo


class FonteDadosBrutos(Protocol):
    """Porta de entrada. Hoje: Excel. Amanhã: listas do SharePoint."""
    def ler(self) -> BaseBruta: ...


class RepositorioResultado(Protocol):
    """Porta de saída. Hoje: Excel. Amanhã: SharePoint, banco, BI."""
    def salvar(self, resultado: ResultadoTratamento) -> None: ...


# ═════════════ Operação do dia a dia (depois da carga inicial) ═════════════
class RecusadoPeloBanco(Exception):
    """O adaptador traduz o erro técnico do banco nesta exceção da aplicação."""


class BaseOperacional(Protocol):
    """Porta da base única em operação. Protótipo: SQLite. Produção: SharePoint/Dataverse/SQL."""
    def existe_veiculo(self, codigo: str) -> bool: ...
    def ultima_leitura(self, codigo: str, ate: Any) -> LeituraKm | None: ...
    def inserir_leitura(self, leitura: LeituraKm) -> None: ...
    def ocorrencias_abertas(self) -> list[Ocorrencia]: ...
    def proximo_id_ocorrencia(self) -> str: ...
    def inserir_ocorrencia(self, ocorrencia: Ocorrencia) -> None: ...
    def fechar_ocorrencia(self, ocorrencia_id: str, data: Any) -> None: ...
    def registrar_status_frota(self, codigo: str, data: Any, status: str, motivo: str | None, previsao: Any) -> None: ...
    def registrar_teste_realizado(self, teste_id: str, data: Any) -> None: ...
    def resolver_pendencia(self, pendencia_id: int) -> None: ...
