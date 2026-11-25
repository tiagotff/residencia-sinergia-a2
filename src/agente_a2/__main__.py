"""Linha de comando do A2.

    python -m agente_a2 ingerir                 # PDFs de bases_pdf/ -> índice (memória ou pgvector)
    python -m agente_a2 exportar saida.json     # o que o parser entendeu de cada PDF (revisão)
    python -m agente_a2 perguntar "minha luva rasgou" [--intencao F5] [--colaborador 42]
    python -m agente_a2 rodar fixtures/a2/responder/f5_relato_luva.tarefa.json
    python -m agente_a2 avaliar                 # recall@1/@3 e acerto de base usando as variações
    python -m agente_a2 calibrar                # sugere RAG_LIMIAR_COSSENO para o modelo de embeddings
    python -m agente_a2 extrair [--dias 30]     # planilha de análise + dataset das interações gravadas
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import ConfigA2


def _carregar_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    _carregar_env()
    ap = argparse.ArgumentParser(prog="agente_a2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingerir")
    s.add_argument("--pasta", type=Path)
    s = sub.add_parser("exportar")
    s.add_argument("destino", type=Path)
    s.add_argument("--pasta", type=Path)
    s = sub.add_parser("perguntar")
    s.add_argument("pergunta")
    s.add_argument("--intencao")
    s.add_argument("--colaborador", type=int, default=42)
    s = sub.add_parser("rodar")
    s.add_argument("tarefa", type=Path)
    sub.add_parser("avaliar")
    sub.add_parser("calibrar")
    s = sub.add_parser("extrair")
    s.add_argument("--dias", type=int)
    s.add_argument("--pasta", type=Path, default=Path("exportacoes"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    cfg = ConfigA2()
    if args.cmd == "exportar":
        from .rag.ingestao import exportar_json

        exportar_json(args.pasta or cfg.pasta_bases, args.destino)
        print(f"exportado em {args.destino}")
        return 0

    from .agente import criar_agente_a2

    agente = criar_agente_a2(cfg)
    rec = agente.dep.recuperador
    hoje = datetime.now(ZoneInfo(cfg.fuso)).date()

    if args.cmd == "ingerir":
        from .rag.ingestao import ingerir_pasta

        rel = ingerir_pasta(args.pasta or cfg.pasta_bases, rec.store, rec.embedder)
        print(json.dumps(rel, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "avaliar":
        from .avaliacao import avaliar

        print(avaliar(rec, hoje).texto())
        return 0
    if args.cmd == "extrair":
        from .extracao import extrair, perguntas_do_indice

        if agente.registro is None:
            print("Registro de interações desligado (A2_REGISTRAR_INTERACOES=0).")
            return 1
        print(f"Banco: {agente.registro.descricao}")
        res = extrair(agente.registro, args.pasta, dias=args.dias, fuso=cfg.fuso,
                      perguntas_bases=perguntas_do_indice(rec.store, hoje))
        for k, v in res.items():
            print(f"  {k:18} {v}")
        return 0
    if args.cmd == "calibrar":
        from .avaliacao import calibrar

        print(calibrar(rec, hoje))
        return 0

    if args.cmd == "perguntar":
        id_t = f"t-cli-{uuid.uuid4().hex[:8]}"
        tarefa = {
            "protocolo": "sinergia/1", "id_mensagem": id_t, "tipo": "TAREFA", "acao": "a2.responder",
            "origem": "A0", "destino": "A2",
            "correlacao": {"id_caso": None, "thread_id": f"cli-{args.colaborador}", "id_tarefa": id_t},
            "contexto": {"id_colaborador": args.colaborador, "id_empresa": 1, "perfil": "colaborador",
                         "canal": "chat", "data_hora": datetime.now(ZoneInfo(cfg.fuso)).isoformat(timespec="seconds")},
            "payload": {"pergunta": args.pergunta, "intencao": args.intencao},
        }
    else:
        tarefa = json.loads(args.tarefa.read_text(encoding="utf-8"))

    resultado = agente.executar(tarefa)
    print(resultado.model_dump_json(indent=2, exclude_none=False))
    return 0 if resultado.status != "ERRO" else 1


if __name__ == "__main__":
    sys.exit(main())
