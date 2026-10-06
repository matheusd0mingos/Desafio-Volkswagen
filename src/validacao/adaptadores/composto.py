"""Composite: salva em vários destinos com uma chamada só (ex.: Excel + SQLite)."""
from ..aplicacao.portas import RepositorioResultado, ResultadoTratamento


class RepositorioComposto:
    def __init__(self, *repositorios: RepositorioResultado) -> None:
        self._repos = repositorios

    def salvar(self, resultado: ResultadoTratamento) -> None:
        for r in self._repos:
            r.salvar(resultado)
