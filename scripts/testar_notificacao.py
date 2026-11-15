"""Etapa 7: manda as ofertas aprovadas que estão no banco como notificação de teste.

Não marca nada como notificado (é só teste).
Uso: python -m scripts.testar_notificacao
"""
from __future__ import annotations

from app.avaliacao import Criterios
from app.banco import Banco
from app.notificacao import Bot, formatar


def main() -> None:
    aprovadas = Banco().aprovadas()
    if not aprovadas:
        print("Nenhuma oferta aprovada no banco. Rode antes: python -m scripts.gravar")
        return
    bot = Bot()
    teto = Criterios.carregar().preco_max
    for r in aprovadas:
        m = formatar(r, teto=teto, teste=True)
        bot.enviar(m.texto, m.botoes)
        print(f"Enviada: {r['modelo']} · R$ {r['preco']}")


if __name__ == "__main__":
    main()
