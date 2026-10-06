"""Raiz de composição: escolhe os adaptadores pela extensão de cada saída.

validacao entrada.xlsx saida.xlsx [base.db ...]
"""
import sys
from pathlib import Path

from .adaptadores.composto import RepositorioComposto
from .adaptadores.excel import ExcelFonte, ExcelRepositorio
from .adaptadores.sqlite.repositorio import SqliteRepositorio
from .aplicacao.tratar_base import TratarBaseDeValidacao

ADAPTADORES = {".xlsx": ExcelRepositorio, ".db": SqliteRepositorio, ".sqlite": SqliteRepositorio}


def main() -> None:
    entrada = sys.argv[1] if len(sys.argv) > 1 else "Case_Dados_Validacao_.xlsx"
    saidas = sys.argv[2:] or ["Case_Dados_Tratados.xlsx", "validacao.db"]
    if not Path(entrada).is_file():
        sys.exit(f"Arquivo de entrada não encontrado: {entrada}\n"
                 "No Docker: coloque o Excel em ./dados/entrada/ com o nome Case_Dados_Validacao_.xlsx")
    try:
        repo = RepositorioComposto(*(ADAPTADORES[Path(s).suffix.lower()](s) for s in saidas))
    except KeyError as e:
        sys.exit(f"Extensão de saída não suportada: {e}. Use .xlsx, .db ou .sqlite")
    r = TratarBaseDeValidacao(ExcelFonte(entrada), repo).executar().resumo
    print(f"Falhas abertas: {r.falhas_abertas_antes} → {r.falhas_abertas_depois}")
    print(f"Km rodado: {r.km_rodado_bruto:,.0f} (bruto) → {r.km_rodado_tratado:,.0f} (tratado)")
    print(f"{r.total_achados} achados no log · corte {r.corte:%d/%m/%Y} · saídas: {', '.join(saidas)}")


if __name__ == "__main__":
    main()
