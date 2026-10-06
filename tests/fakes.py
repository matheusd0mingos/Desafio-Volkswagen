"""Adaptadores falsos: provam que o núcleo roda sem Excel nem pandas."""
from validacao.aplicacao.portas import BaseBruta, ResultadoTratamento


class FonteEmMemoria:
    def __init__(self, base: BaseBruta) -> None:
        self._base = base

    def ler(self) -> BaseBruta:
        return self._base


class RepositorioEmMemoria:
    def __init__(self) -> None:
        self.salvo: ResultadoTratamento | None = None

    def salvar(self, resultado: ResultadoTratamento) -> None:
        self.salvo = resultado
