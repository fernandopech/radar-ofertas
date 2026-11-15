"""Interface das fontes plugáveis.

Cada fonte (Telegram, Mercado Livre, OLX...) implementa `Fonte` e entrega
`Oferta`s pelo callback. Tudo depois disso é igual pra qualquer fonte.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from app.oferta import Oferta

AoReceber = Callable[[Oferta], Awaitable[None]]


class Fonte(ABC):
    #: identificador curto, ex.: "telegram"
    nome: str

    @abstractmethod
    async def executar(self, ao_receber: AoReceber, recuperar: int = 0) -> None:
        """Roda pra sempre entregando ofertas novas.

        `recuperar`: ao iniciar, entrega também as últimas N mensagens/anúncios
        (quem recebe ignora as que já estão no banco). Cobre reinícios e quedas.
        Fontes push (Telegram) escutam eventos; fontes de polling
        (marketplaces) fazem um loop com intervalo generoso.
        """
