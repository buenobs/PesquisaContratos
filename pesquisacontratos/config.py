"""Configuração central: caminhos padrão e leitura do .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "pesquisacontratos.db"
DOWNLOADS_DIR = BASE_DIR / "downloads"

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct").strip()
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

HTTP_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 PesquisaContratos/0.1"
)


def ia_configurada() -> bool:
    return bool(NVIDIA_API_KEY)
