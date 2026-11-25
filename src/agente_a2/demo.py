"""Cadastro fictício para demonstração (usado quando não há DATABASE_URL)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .repositorio import EPI, Colaborador, RepositorioMemoria


def repositorio_demo(fuso: str = "America/Sao_Paulo") -> RepositorioMemoria:
    hoje = datetime.now(ZoneInfo(fuso)).date()
    return RepositorioMemoria(
        colaboradores={
            42: Colaborador(42, "Carla Souza", 15, "Auxiliar de câmara fria", "07:00", "16:00"),
            57: Colaborador(57, "Bruno Lima", 16, "Operador de empilhadeira", "08:00", "17:00"),
            63: Colaborador(63, "Ana Reis", 17, "Atendente de teleatendimento", "09:00", "15:00"),
        },
        epis={7: EPI(7, "Luva térmica"), 8: EPI(8, "Luva anticorte"), 12: EPI(12, "Protetor auricular"),
              14: EPI(14, "Calçado de segurança")},
        cargo_epis={15: [7, 8, 14], 16: [12, 14], 17: []},
        periodos=[(63, hoje, hoje + timedelta(days=7), "ferias")],
    )


def situacao_hoje(repo: RepositorioMemoria, id_colaborador: int, fuso: str = "America/Sao_Paulo") -> str:
    return repo.situacao(id_colaborador, datetime.now(ZoneInfo(fuso)).date()).estado

