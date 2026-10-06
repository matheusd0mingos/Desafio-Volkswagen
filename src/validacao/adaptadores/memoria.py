"""Repositório em memória: para quem só quer o resultado (ex.: o painel web)."""
from ..aplicacao.portas import ResultadoTratamento


class RepositorioEmMemoria:
    def __init__(self) -> None:
        self.salvo: ResultadoTratamento | None = None

    def salvar(self, resultado: ResultadoTratamento) -> None:
        self.salvo = resultado
