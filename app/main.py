"""Monitor 24h: escuta as fontes, processa, grava no Supabase e notifica pelo bot.

Uso: python -m app.main
Variáveis opcionais: RECUPERAR_AO_INICIAR (padrão 30 mensagens por canal).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from app.avaliacao import Criterios
from app.banco import Banco
from app.config import ConfigTelegram, SessaoInvalida
from app.dedup import decidir
from app.fontes.olx import ConfigOlx, FonteOlx
from app.fontes.telegram import FonteTelegram
from app.notificacao import Bot, formatar
from app.notificacao.resumo import formatar_resumo, proximo_envio
from app.oferta import Oferta
from app.processamento import processar, registro

log = logging.getLogger("monitor")


class Monitor:
    def __init__(self, banco: Banco, bot: Bot, criterios: Criterios):
        self.banco, self.bot, self.c = banco, bot, criterios
        self._lock = asyncio.Lock()  # uma oferta por vez (IA, site e banco sem corrida)

    async def ao_receber(self, oferta: Oferta) -> None:
        async with self._lock:
            # processar() faz chamadas de rede síncronas: roda fora do loop do Telethon
            await asyncio.to_thread(self.tratar, oferta)

    def tratar(self, oferta: Oferta) -> None:
        try:
            if self.banco.ja_existe(oferta.fonte, oferta.id_externo):
                return
        except Exception:
            log.exception("Banco indisponível ao checar %s; processando assim mesmo", oferta.id_externo)

        dias = int((self.c.bruto.get("usados") or {}).get("comparaveis_dias", 30))
        p = processar(oferta, self.c,
                      comparaveis=lambda gpu, ram: self.banco.precos_comparaveis(gpu, ram, dias))
        reg = registro(p)
        specs = p.extracao.specs
        nome = specs.modelo if specs and specs.modelo else p.extracao.metodo
        id_oferta = None
        try:
            id_oferta = self.banco.gravar(reg)
        except Exception:
            log.exception("Não consegui gravar %s no banco", oferta.id_externo)

        if not p.deve_notificar:
            log.info("· %s → %s", nome, p.resultado.motivo if p.resultado else "não é notebook")
            return
        idade_h = (datetime.now(timezone.utc) - oferta.recebida_em).total_seconds() / 3600
        limite_h = (self.c.notificar_ate_horas_marketplace if oferta.categoria_confirmada
                    else self.c.notificar_ate_horas)
        if idade_h > limite_h:
            motivo = f"oferta antiga ({idade_h:.0f} h), recuperada ao iniciar"
            log.info("· %s → aprovada, mas %s", nome, motivo)
            if id_oferta is not None:
                try:
                    self.banco.anotar(id_oferta, {"motivo_nao_notificado": motivo})
                except Exception:
                    log.exception("Não consegui anotar %s", nome)
            return
        decisao = self._dedup(reg)
        if not decisao.notificar:
            log.info("· %s → aprovada, mas %s", nome, decisao.motivo)
            if id_oferta is not None:
                try:
                    self.banco.anotar(id_oferta, {"motivo_nao_notificado": decisao.motivo})
                except Exception:
                    log.exception("Não consegui anotar %s", nome)
            return
        m = formatar(reg, teto=self.c.preco_max, queda_de=decisao.queda_de)
        try:
            self.bot.enviar(m.texto, m.botoes)
        except Exception:
            log.exception("Falha ao notificar %s", nome)
            return
        log.info("✉ NOTIFICADO: %s · %s", nome, p.resultado.motivo)
        if id_oferta is not None:
            try:
                self.banco.marcar_notificado(id_oferta, datetime.now(timezone.utc).isoformat())
            except Exception:
                log.exception("Não consegui marcar %s como notificado", nome)


    def _dedup(self, reg: dict):
        """Mesmo modelo já avisado na janela: só avisa de novo se o preço caiu."""
        chave = reg.get("chave_modelo")
        if not chave:
            return decidir(reg.get("preco"), None, self.c.queda_minima_reais)
        desde = (datetime.now(timezone.utc) - timedelta(hours=self.c.dedup_horas)).isoformat()
        try:
            anterior = self.banco.ultima_notificacao(chave, desde)
        except Exception:
            log.exception("Banco indisponível no dedup; notificando por garantia")
            anterior = None
        return decidir(reg.get("preco"), anterior, self.c.queda_minima_reais)


AVISO_SESSAO = (
    "⚠️ <b>Parei de ler os canais</b>: o Telegram derrubou o login da sua conta no monitor.\n\n"
    "No Codespace, rode:\n"
    "<code>python -m scripts.login_telegram</code>\n"
    "<code>bash scripts/deploy_heroku.sh</code>\n\n"
    "Dica: não rode scripts do Telegram no Codespace com o monitor ligado no Heroku "
    "(a mesma sessão em dois lugares faz o Telegram derrubar o login)."
)


async def _rodar_telegram(monitor: "Monitor", recuperar: int) -> None:
    fonte = FonteTelegram(ConfigTelegram.carregar())
    try:
        await fonte.executar(monitor.ao_receber, recuperar=recuperar)
    except SessaoInvalida:
        log.error("Sessão do Telegram derrubada; avisando pelo bot e aguardando novo login.")
        try:
            monitor.bot.enviar(AVISO_SESSAO)
        except Exception:
            log.exception("Nem o aviso pelo bot saiu")
        # Fica parado em vez de cair: cair faz o Heroku reiniciar sem parar (e avisar sem parar).
        # O Heroku reinicia o processo 1x por dia, então o aviso se repete no máximo 1x/dia.
        # As outras fontes (OLX) continuam rodando.
        await asyncio.sleep(24 * 3600)


async def _resumo_semanal(monitor: "Monitor") -> None:
    cfg = monitor.c.bruto.get("resumo_semanal") or {}
    if not cfg.get("ativo"):
        return
    dia, hora = str(cfg.get("dia", "domingo")), int(cfg.get("hora", 19))
    itens_max, nota_min = int(cfg.get("itens", 10)), float(cfg.get("nota_min", 5))
    while True:
        alvo = proximo_envio(datetime.now(timezone.utc), dia, hora)
        log.info("Resumo semanal agendado para %s", alvo.strftime("%d/%m %H:%M"))
        await asyncio.sleep(max(1.0, (alvo - datetime.now(timezone.utc)).total_seconds()))
        try:
            itens = await asyncio.to_thread(monitor.banco.quase_da_semana, nota_min,
                                            monitor.c.nota_minima_usado, itens_max)
            await asyncio.to_thread(monitor.bot.enviar, formatar_resumo(itens))
            log.info("Resumo semanal enviado (%d itens)", len(itens))
        except Exception:
            log.exception("Falha no resumo semanal")
        await asyncio.sleep(120)  # evita disparar duas vezes no mesmo minuto


async def rodar() -> None:
    criterios = Criterios.carregar()
    monitor = Monitor(Banco(), Bot(), criterios)
    if not monitor.bot.chat_id:
        raise SystemExit("BOT_CHAT_ID vazio. Rode: python -m scripts.configurar_bot")
    recuperar = int(os.getenv("RECUPERAR_AO_INICIAR", "30"))
    log.info("Monitor iniciado · teto R$ %.0f · nota mínima %g", criterios.preco_max, criterios.nota_minima)

    tarefas = [_rodar_telegram(monitor, recuperar), _resumo_semanal(monitor)]
    cfg_olx = ConfigOlx.carregar(criterios.bruto)
    if cfg_olx:
        tarefas.append(FonteOlx(cfg_olx, ja_existe=monitor.banco.ja_existe).executar(monitor.ao_receber))
    else:
        log.info("OLX desligada (sem RAPIDAPI_KEY ou olx.ativo=false no criterios.yaml)")
    await asyncio.gather(*tarefas)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("telethon").setLevel(logging.WARNING)
    try:
        asyncio.run(rodar())
    except KeyboardInterrupt:
        log.info("Parado.")


if __name__ == "__main__":
    main()
