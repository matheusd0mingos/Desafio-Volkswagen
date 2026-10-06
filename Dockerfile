# syntax=docker/dockerfile:1

# ───────── 1. builder: empacota o projeto + dependências em wheels ─────────
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels ".[painel]"

# ───────── 2. teste: instala o PACOTE (não o src) e roda pytest ─────────
# Testa o que vai para produção, não a pasta de código.
FROM python:3.12-slim AS teste
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels validacao && pip install "pytest>=8"
COPY pyproject.toml ./
COPY tests ./tests
CMD ["pytest", "-q"]

# ───────── 3. runtime: imagem enxuta, sem compilador, sem testes, sem root ─────────
FROM python:3.12-slim AS runtime
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels validacao \
 && rm -rf /wheels \
 && useradd --create-home --uid 1000 app
USER app
WORKDIR /dados
ENTRYPOINT ["validacao"]
CMD ["entrada/Case_Dados_Validacao_.xlsx", "saida/Case_Dados_Tratados.xlsx", "saida/validacao.db"]

# ───────── 4. painel: Streamlit interativo em http://localhost:8501 ─────────
FROM python:3.12-slim AS painel
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CASE_XLSX=/dados/entrada/Case_Dados_Validacao_.xlsx \
    BASE_DB=/dados/base/validacao.db
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels "validacao[painel]" \
 && rm -rf /wheels \
 && useradd --create-home --uid 1000 app
USER app
WORKDIR /dados
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["validacao-painel"]
