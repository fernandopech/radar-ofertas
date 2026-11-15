"""Formato comum que toda fonte entrega ao pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

Condicao = Literal["novo", "recondicionado", "usado", "desconhecido"]


@dataclass(frozen=True)
class Oferta:
    fonte: str                       # ex.: "telegram:achadosdotb"
    id_externo: str                  # único dentro da fonte (dedup)
    texto: str                       # texto/legenda bruto
    recebida_em: datetime
    link: str | None = None          # link da oferta (loja), se achado
    link_origem: str | None = None   # link do post na fonte (ex.: t.me/canal/123)
    preco_bruto: str | None = None   # só se a fonte informar estruturado
    condicao: Condicao | None = None # só se a fonte informar
    tem_imagem: bool = False         # pra medir se vale ler imagens na v2
    links_extras: tuple[str, ...] = field(default_factory=tuple)
    # A fonte garante que é notebook (ex.: categoria Notebooks da OLX): pula o pré-filtro.
    categoria_confirmada: bool = False
    local: str | None = None         # cidade/bairro, quando a fonte informa (marketplaces)

    def para_dict(self) -> dict:
        d = asdict(self)
        d["recebida_em"] = self.recebida_em.isoformat()
        d["links_extras"] = list(self.links_extras)
        return d
