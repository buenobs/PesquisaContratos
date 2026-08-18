"""Configuração central: caminhos padrão e leitura do .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

def _diretorio_base() -> Path:
    """Onde ficam o .env, o cache SQLite e a pasta de downloads.

    Nao pode ser derivado so de __file__: fora de uma instalacao editavel
    (`pip install -e .`) isso apontaria para dentro do site-packages, e o
    programa tentaria gravar o banco e os PDFs junto com o proprio pacote.

    Ordem de preferencia:
    1. PESQUISACONTRATOS_DIR, quando definido;
    2. a raiz do repositorio, quando rodando de um checkout (uso em dev);
    3. o diretorio de dados do usuario.
    """
    escolhido = os.getenv("PESQUISACONTRATOS_DIR", "").strip()
    if escolhido:
        return Path(escolhido).expanduser().resolve()

    raiz_repo = Path(__file__).resolve().parent.parent
    if (raiz_repo / "pyproject.toml").is_file():
        return raiz_repo

    if os.name == "nt":
        raiz_dados = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        raiz_dados = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return raiz_dados / "PesquisaContratos"


BASE_DIR = _diretorio_base()

# Um .env ao lado dos dados tem prioridade; senao procura a partir do diretorio
# atual, para quem roda a CLI de dentro de outro projeto.
if not load_dotenv(BASE_DIR / ".env"):
    load_dotenv()

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
