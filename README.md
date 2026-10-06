# Tratamento dos dados de validação — arquitetura hexagonal

```
src/validacao/
├── dominio/        ← regras de negócio puras (sem pandas, sem I/O)
│   ├── modelos.py        entidades, Achado, Config
│   ├── normalizadores.py ID, data, status, pessoa, catálogo
│   ├── regras.py         1 regra = 1 classe (Strategy)
│   └── servicos.py       validador de km, duplicatas, status calculado
├── aplicacao/
│   ├── portas.py         FonteDadosBrutos, RepositorioResultado (Protocol)
│   └── tratar_base.py    caso de uso: orquestra domínio + portas
├── adaptadores/
│   └── excel.py          único arquivo que conhece pandas
└── __main__.py           raiz de composição (liga adaptador ↔ porta)
tests/                    separado; usa adaptadores em memória
```

Rodar: `PYTHONPATH=src python -m validacao Case_Dados_Validacao_.xlsx saida.xlsx`
Testar: `pip install -e .[dev] && pytest` (o teste de integração roda se o Excel estiver na raiz)

Trocar Excel por SharePoint = escrever `adaptadores/sharepoint.py` com `ler()` e `salvar()`. Domínio e testes não mudam.

## Docker

```
dados/entrada/Case_Dados_Validacao_.xlsx   ← coloque o Excel aqui
make build && make test && make run        → dados/saida/Case_Dados_Tratados.xlsx
```

| Estágio | Para quê |
|---|---|
| `builder` | gera wheels do projeto + dependências |
| `teste` | instala o **pacote** e roda pytest (testa o que vai para produção) |
| `runtime` | imagem enxuta, sem testes, usuário não-root, entrada read-only |

Sem make: `docker compose run --rm testes` e `docker compose run --rm tratar`.

## Painel interativo (Streamlit)

```powershell
docker compose up --build -d painel     # abre em http://localhost:8501
docker compose logs -f painel           # ver logs
docker compose down                     # desligar
```
Sem Docker: `pip install -e .[painel]` e depois `validacao-painel`.
O painel é um adaptador primário: chama o mesmo caso de uso, sem duplicar regra.

## Base única em SQLite

`validacao entrada.xlsx saida.xlsx validacao.db` grava Excel **e** SQLite (Composite).
- `src/validacao/adaptadores/sqlite/schema.sql`: o modelo de dados (1.2) com as regras de entrada (1.3) como CONSTRAINTs nomeadas.
- `pendencia`: o que foi barrado, e por quem (domínio ou banco).
- `vw_gate_programa`: o Gate Review em uma consulta SQL.

## Plataforma (fluxo desejado funcionando)

1. **Carga inicial:** na primeira vez, o Excel de `dados/entrada/` é tratado e vira `dados/base/validacao.db`.
2. **Operação:** os engenheiros lançam km, ocorrências, status da frota e testes pela plataforma.
   Cada lançamento passa pelo domínio (regras entre linhas) e pelo banco (constraints).
3. **Pendências:** o que a carga inicial barrou fica com o dono, que aceita a sugestão, corrige ou descarta.
4. **Gate ao vivo:** lê a base única; muda no instante em que alguém lança.

`docker compose up --build -d painel` → http://localhost:8501 · "Reiniciar base" no Gate ao vivo refaz a carga.
