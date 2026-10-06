"""Carga inicial: o Excel entra UMA vez. Depois, a base é atualizada pela plataforma."""
from __future__ import annotations

import io
from pathlib import Path

from ...aplicacao.tratar_base import TratarBaseDeValidacao
from ...dominio.modelos import Config
from ..excel import ExcelFonte
from .repositorio import SqliteRepositorio


def garantir_base(db: str | Path, excel: bytes, reiniciar: bool = False, config: Config = Config()) -> bool:
    """Cria a base a partir do Excel se ela não existir (ou se pedirem para reiniciar). Devolve True se criou."""
    db = Path(db)
    if db.exists() and not reiniciar:
        return False
    TratarBaseDeValidacao(ExcelFonte(io.BytesIO(excel)), SqliteRepositorio(db), config).executar()
    return True
