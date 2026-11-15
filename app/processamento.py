"""Pipeline completo de uma oferta: extrair → avaliar → montar registro do banco."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.avaliacao import Criterios, Resultado, avaliar
from app.avaliacao.componentes import Classe
from app.dedup import chave_modelo
from app.extracao import Extracao, extrair
from app.oferta import Oferta


@dataclass
class Processada:
    oferta: Oferta
    extracao: Extracao
    resultado: Resultado | None  # None quando não é oferta de notebook

    @property
    def deve_notificar(self) -> bool:
        return bool(self.resultado and self.resultado.aprovado)


def processar(oferta: Oferta, c: Criterios, *, usar_ia: bool = True, usar_site: bool = True,
              comparaveis=None) -> Processada:
    e = extrair(oferta, usar_ia=usar_ia)
    if not e.specs or not e.specs.eh_oferta_notebook:
        return Processada(oferta, e, None)
    return Processada(oferta, e, avaliar(oferta, e.specs, c, usar_ia=usar_ia, usar_site=usar_site,
                                         comparaveis=comparaveis))


def _classes_json(classes: dict) -> dict:
    return {k: ({"nivel": v.nivel, "termo": v.termo} if isinstance(v, Classe) else v)
            for k, v in classes.items()}


def _link_valido(o: Oferta) -> str | None:
    if o.link and o.link.startswith("http") and "\n" not in o.link:
        return o.link
    m = re.search(r"https?://\S+", o.texto)  # amostras antigas tinham o link cortado
    return m.group(0).rstrip(").,;") if m else None


def registro(p: Processada) -> dict[str, Any]:
    o, e, r = p.oferta, p.extracao, p.resultado
    reg: dict[str, Any] = {
        "fonte": o.fonte, "id_externo": o.id_externo, "recebida_em": o.recebida_em.isoformat(),
        "texto_original": o.texto, "link": _link_valido(o), "link_origem": o.link_origem,
        "tem_imagem": o.tem_imagem, "metodo_extracao": e.metodo,
        "aprovado": False, "oportunidade": False, "local": o.local,
        "eh_oferta_notebook": e.specs.eh_oferta_notebook if e.specs else (False if e.metodo == "prefiltro" else None),
    }
    if e.specs:
        s = e.specs.model_dump()
        s.pop("eh_oferta_notebook")
        # texto vazio vira NULL no banco (fica mais fácil filtrar)
        reg.update({k: (None if v == "" else v) for k, v in s.items()})
        reg["chave_modelo"] = chave_modelo(e.specs.modelo, e.specs.gpu, e.specs.ram_gb,
                                           e.specs.armazenamento_gb)
    if r:
        reg.update({
            "passou_regras_duras": r.regras.passou,
            "motivo_reprovacao": "; ".join(r.regras.motivos) or None,
            "dados_ausentes": r.regras.ausentes or None,
            "classes": _classes_json(r.regras.classes) or None,
            "aprovado": r.aprovado,
            "oportunidade": r.oportunidade,
            "desconto_pct": round(r.desconto_pct, 2) if r.desconto_pct is not None else None,
            "alerta_golpe": r.suspeito,
        })
        if r.ficha:
            reg.update({"ficha": r.ficha.campos or None,
                        "preco_justo_min": r.ficha.preco_justo_min,
                        "preco_justo_max": r.ficha.preco_justo_max})
            if r.ficha.loja and not reg.get("loja"):
                reg["loja"] = r.ficha.loja
            if r.ficha.ram_expansivel is not None and reg.get("ram_expansivel") is None:
                reg["ram_expansivel"] = r.ficha.ram_expansivel
                reg["ram_dual_channel"] = r.ficha.ram_dual_channel
        if r.avaliacao:
            aval = r.avaliacao.model_dump()
            if r.usado:
                aval["calculo_usado"] = r.usado.para_dict()
            reg.update({"nota": r.avaliacao.nota, "avaliacao_json": aval})
    return reg
