"""Configuración de la API."""

import os

# ── Base de datos ─────────────────────────────────────
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "divisas.db")
)

# ── JWT ───────────────────────────────────────────────
SECRET_KEY = "divisas-api-secret-2024-cambiar-en-produccion"
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HORAS = 24

# ── Puntos y divisas ──────────────────────────────────
PUNTOS  = ["El Llanito", "Carabobo", "Yesica"]
DIVISAS = ["USD", "COP", "BsF", "EUR"]
SIMBOLOS = {"USD": "$", "COP": "$", "BsF": "Bs", "EUR": "€"}

PARES_TASA  = [("USD", "COP"), ("BsF", "COP")]
DIVISA_BASE = "COP"

CATEGORIAS_GASTOS = [
    "Alimentación", "Transporte", "Servicios",
    "Arriendo / Vivienda", "Personal / Salud",
    "Negocio / Inversión", "Otro",
]
