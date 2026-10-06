"""Normalizadores: valor bruto → Normalizado(valor, achados). Sem efeito colateral."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Protocol

from .modelos import Achado, Normalizado, Origem, Severidade
from .texto import sem_acento, vazio


class Normalizador(Protocol):
    def normalizar(self, valor, origem: Origem, campo: str) -> Normalizado: ...


class VeiculoIDNormalizador:
    def normalizar(self, valor, origem, campo="Veículo") -> Normalizado:
        m = re.search(r"(\d+)", str(valor))
        if not m:
            return Normalizado(None, (Achado(origem, campo, str(valor), "ID ilegível", Severidade.ALTA, "Quarentena"),))
        novo = f"PT-{int(m.group(1)):02d}"
        if str(valor).strip() == novo:
            return Normalizado(novo)
        return Normalizado(novo, (Achado(origem, campo, str(valor), "ID fora do padrão PT-NN",
                                         Severidade.MEDIA, f"Padronizado → {novo}"),))


class DataNormalizador:
    """Premissa: data ambígua segue dd/mm (padrão brasileiro)."""

    def normalizar(self, valor, origem, campo) -> Normalizado:
        if vazio(valor):
            return Normalizado(None)
        if isinstance(valor, datetime):
            return Normalizado(valor.date())
        if isinstance(valor, date):
            return Normalizado(valor)
        s = str(valor).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            regra, d = "Data como texto ISO", date.fromisoformat(s)
        else:
            a, b, c = map(int, s.split("/"))
            if b > 12:
                regra, d = "Data em formato americano mm/dd", date(c, a, b)
            else:
                regra, d = "Data como texto dd/mm/aaaa", date(c, b, a)
        sev = Severidade.ALTA if "americano" in regra else Severidade.BAIXA
        return Normalizado(d, (Achado(origem, campo, str(valor), regra, sev, f"Convertido → {d:%Y-%m-%d}"),))


class StatusNormalizador:
    def __init__(self, catalogo: dict[str, str]) -> None:
        self._catalogo = catalogo

    def normalizar(self, valor, origem, campo="Status") -> Normalizado:
        novo = self._catalogo.get(sem_acento(valor))
        if novo is None:
            return Normalizado("Indefinido", (Achado(origem, campo, str(valor), "Status fora da lista",
                                                     Severidade.ALTA, "Marcado como 'Indefinido' — dono deve informar"),))
        if valor == novo:
            return Normalizado(novo)
        return Normalizado(novo, (Achado(origem, campo, str(valor), "Status com grafia diferente",
                                         Severidade.MEDIA, f"Padronizado → {novo}"),))


class PessoaNormalizador:
    def __init__(self, canonicos: list[str]) -> None:
        self._canonicos = canonicos

    @staticmethod
    def _casa(partes: list[str], canonico: str) -> bool:
        cs = sem_acento(canonico).split()
        return ((partes[-1] == cs[-1] and partes[0][0] == cs[0][0]) or
                (partes[0] == cs[0] and cs[-1].startswith(partes[-1])))

    def normalizar(self, valor, origem, campo="Responsável") -> Normalizado:
        if vazio(valor):
            return Normalizado(None)
        partes = sem_acento(valor).replace(".", "").split()
        for c in self._canonicos:
            if self._casa(partes, c):
                if valor == c:
                    return Normalizado(c)
                return Normalizado(c, (Achado(origem, campo, str(valor), "Nome fora do padrão",
                                              Severidade.BAIXA, f"Padronizado → {c}"),))
        return Normalizado(valor, (Achado(origem, campo, str(valor), "Pessoa não reconhecida",
                                          Severidade.MEDIA, "Quarentena"),))


class CatalogoNormalizador:
    def __init__(self, catalogo: dict[str, str], regra: str) -> None:
        self._catalogo, self._regra = catalogo, regra

    def normalizar(self, valor, origem, campo) -> Normalizado:
        novo = self._catalogo.get(sem_acento(valor))
        if novo is None:
            return Normalizado(valor)
        return Normalizado(novo, (Achado(origem, campo, str(valor), self._regra, Severidade.MEDIA, f"Padronizado → {novo}"),))


class OcorrenciaIDNormalizador:
    """Tem estado (IDs já vistos): instanciar uma vez por execução."""

    def __init__(self) -> None:
        self._vistos: set[str] = set()

    def normalizar(self, valor, origem, campo="ID") -> Normalizado:
        achados: list[Achado] = []
        if vazio(valor):
            novo = f"OC-SEMID-{origem.linha}"
            achados.append(Achado(origem, campo, "vazio", "Ocorrência sem ID", Severidade.ALTA, f"ID provisório {novo}"))
        else:
            novo = f"OC-{int(re.search(r'\d+', str(valor)).group()):04d}"
            if not str(valor).isdigit():
                achados.append(Achado(origem, campo, str(valor), "ID fora do padrão", Severidade.MEDIA, f"Padronizado → {novo}"))
        if novo in self._vistos:
            achados.append(Achado(origem, campo, str(valor), "ID duplicado", Severidade.ALTA, f"Renomeado {novo}-B, dono revisa"))
            novo += "-B"
        self._vistos.add(novo)
        return Normalizado(novo, tuple(achados))
