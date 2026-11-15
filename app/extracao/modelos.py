"""Formato das specs extraídas (saída da etapa 1)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# A API de saída estruturada aceita no máximo 16 campos que podem ser nulos.
# Por isso: texto ausente = "" ; só números e sim/não podem ser null.
CAMPOS_TEXTO = (
    "modelo", "marca", "cpu", "gpu", "tipo_armazenamento", "tela_tipo",
    "sistema", "preco_parcelado", "cupom", "loja", "link",
)


class Specs(BaseModel):
    """Dados que a oferta não informa ficam vazios ("" ou null). Nunca inventar."""

    eh_oferta_notebook: bool = Field(description="false se for acessório, monitor, console, aviso, vídeo etc.")
    modelo: str = ""
    marca: str = ""
    cpu: str = Field("", description="ex.: 'Ryzen 7 8840HS', 'Core Ultra 5 225H'")
    gpu: str = Field("", description="ex.: 'Radeon 780M', 'GeForce RTX 4050'")
    gpu_inferida: bool = Field(False, description="true se a GPU foi deduzida pelo processador, não dita na oferta")
    ram_gb: int | None = None
    ram_expansivel: bool | None = None
    ram_dual_channel: bool | None = None
    armazenamento_gb: int | None = Field(None, description="1 TB = 1024")
    tipo_armazenamento: str = Field("", description="SSD, HD, eMMC, eUFS")
    tela_pol: float | None = None
    tela_tipo: str = Field("", description="ex.: 'Full HD IPS 144 Hz', 'WUXGA IPS', 'OLED'")
    sistema: str = Field("", description="'Windows', 'Linux', 'sem sistema', 'macOS', 'ChromeOS'")
    preco: float | None = Field(None, description="menor preço à vista em R$, já com cupom se a oferta disser")
    preco_parcelado: str = ""
    cupom: str = Field("", description="código do cupom, ou 'sim' se exige cupom sem dizer o código")
    condicao: Literal["novo", "recondicionado", "usado", "desconhecido"] = "desconhecido"
    garantia_meses: int | None = None
    vendedor_tipo: Literal["loja", "pessoa_fisica", "desconhecido"] = "desconhecido"
    loja: str = ""
    link: str = ""

    @field_validator(*CAMPOS_TEXTO, mode="before")
    @classmethod
    def _none_vira_vazio(cls, v: object) -> object:
        return "" if v is None else v
