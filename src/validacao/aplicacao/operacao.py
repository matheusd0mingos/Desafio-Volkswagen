"""Casos de uso da operação: o engenheiro lança o dado UMA vez, e ele já entra validado.
Duas barreiras: regras do domínio (comparam linhas) e constraints do banco (via porta)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from ..dominio.modelos import Config, LeituraKm, Ocorrencia
from ..dominio.regras import REGRAS_LEITURA_PADRAO, MesmaDataRule, RegraLeitura, SaltoRule
from ..dominio.servicos import Similaridade
from .portas import BaseOperacional, RecusadoPeloBanco


@dataclass(frozen=True)
class Resposta:
    aceito: bool
    mensagem: str
    pede_confirmacao: bool = False   # o usuário pode confirmar e reenviar


class LancarLeituraKm:
    def __init__(self, base: BaseOperacional, config: Config = Config(),
                 regras: Sequence[RegraLeitura] = REGRAS_LEITURA_PADRAO,
                 confirmaveis: tuple[type, ...] = (SaltoRule,)) -> None:
        self._base, self._cfg, self._regras, self._confirmaveis = base, config, regras, confirmaveis

    def executar(self, codigo: str, data: date, km: float, responsavel: str,
                 confirmado: bool = False, pendencia_id: int | None = None) -> Resposta:
        if not self._base.existe_veiculo(codigo):
            return Resposta(False, f"{codigo} não está no cadastro da frota. Fale com a logística.")
        nova = LeituraKm(codigo, data, data, km, responsavel, None, 0)
        anterior = self._base.ultima_leitura(codigo, ate=data)
        if anterior is not None:
            for regra in self._regras:
                v = regra.avaliar(nova, anterior, self._cfg)
                if v is None:
                    continue
                confirmavel = isinstance(regra, self._confirmaveis)
                if confirmavel and confirmado:
                    break
                ref = f" (última: {anterior.km:,.0f} km em {anterior.data:%d/%m})".replace(",", ".")
                return Resposta(False, f"{v.regra}{ref}. {v.acao}", pede_confirmacao=confirmavel)
        try:
            self._base.inserir_leitura(nova)
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        if pendencia_id is not None:
            self._base.resolver_pendencia(pendencia_id)
        return Resposta(True, f"Leitura de {codigo} registrada: {km:,.0f} km em {data:%d/%m/%Y}.".replace(",", "."))


class SubstituirLeituraKm:
    """Duas leituras no mesmo dia: o dono escolhe a certa. A escolhida ainda precisa
    caber entre a leitura anterior e a seguinte."""

    def __init__(self, base: BaseOperacional, config: Config = Config(),
                 regras: Sequence[RegraLeitura] = REGRAS_LEITURA_PADRAO) -> None:
        self._base, self._cfg = base, config
        self._regras = [r for r in regras if not isinstance(r, MesmaDataRule)]

    def executar(self, codigo: str, data: date, km: float, responsavel: str,
                 pendencia_id: int | None = None) -> Resposta:
        nova = LeituraKm(codigo, data, data, km, responsavel, None, 0)
        antes = self._base.leitura_vizinha(codigo, data, depois=False)
        depois = self._base.leitura_vizinha(codigo, data, depois=True)
        if antes is not None:
            v = next((v for r in self._regras if (v := r.avaliar(nova, antes, self._cfg))), None)
            if v:
                return Resposta(False, f"{v.regra}. {v.acao}")
        if depois is not None and depois.km < km:
            return Resposta(False, f"Fica maior que a leitura seguinte ({depois.km:,.0f} km em "
                                   f"{depois.data:%d/%m}).".replace(",", "."))
        try:
            self._base.substituir_leitura(nova)
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        if pendencia_id is not None:
            self._base.resolver_pendencia(pendencia_id)
        return Resposta(True, f"{codigo} em {data:%d/%m/%Y} agora vale {km:,.0f} km.".replace(",", "."))


class AbrirOcorrencia:
    def __init__(self, base: BaseOperacional, config: Config = Config(),
                 similaridade: Similaridade | None = None) -> None:
        self._base, self._cfg, self._sim = base, config, similaridade or Similaridade()

    def executar(self, codigo: str, descricao: str, data: date, responsavel: str,
                 confirmado: bool = False) -> Resposta:
        if not self._base.existe_veiculo(codigo):
            return Resposta(False, f"{codigo} não está no cadastro da frota.")
        if not descricao.strip():
            return Resposta(False, "Descreva a ocorrência.")
        abertas = self._base.ocorrencias_abertas()
        if not confirmado:
            for o in abertas:
                if o.veiculo == codigo and self._sim(o.descricao, descricao) >= self._cfg.limiar_duplicata:
                    return Resposta(False, f"Parece a mesma falha já aberta: {o.id} — “{o.descricao}”. "
                                           "Se for outra falha, confirme.", pede_confirmacao=True)
        oid = self._base.proximo_id_ocorrencia()
        try:
            self._base.inserir_ocorrencia(Ocorrencia(oid, codigo, descricao.strip(), "Aberto", data, None,
                                                     responsavel, 0, oid))
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        sistemicas = [o for o in abertas if o.veiculo != codigo
                      and self._sim(o.descricao, descricao) >= self._cfg.limiar_sistemica]
        aviso = (" Atenção: falha parecida aberta em " + ", ".join(f"{o.veiculo} ({o.id})" for o in sistemicas)
                 + ". Pode ser sistêmica.") if sistemicas else ""
        return Resposta(True, f"Ocorrência {oid} aberta para {codigo}.{aviso}")


class FecharOcorrencia:
    def __init__(self, base: BaseOperacional) -> None:
        self._base = base

    def executar(self, ocorrencia_id: str, data: date) -> Resposta:
        try:
            self._base.fechar_ocorrencia(ocorrencia_id, data)
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        return Resposta(True, f"{ocorrencia_id} fechada em {data:%d/%m/%Y}.")


class AtualizarStatusFrota:
    def __init__(self, base: BaseOperacional) -> None:
        self._base = base

    def executar(self, codigo: str, data: date, status: str, motivo: str | None, previsao: date | None) -> Resposta:
        try:
            self._base.registrar_status_frota(codigo, data, status, (motivo or "").strip() or None, previsao)
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        return Resposta(True, f"{codigo}: {status} desde {data:%d/%m/%Y}.")


class RegistrarTesteRealizado:
    def __init__(self, base: BaseOperacional) -> None:
        self._base = base

    def executar(self, teste_id: str, data: date) -> Resposta:
        try:
            self._base.registrar_teste_realizado(teste_id, data)
        except RecusadoPeloBanco as e:
            return Resposta(False, str(e))
        return Resposta(True, f"{teste_id} concluído em {data:%d/%m/%Y}. O status é calculado sozinho.")
