"""Configuración de la API."""

import os

# ── Base de datos ─────────────────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:LlfvBchtNO3hMr16@db.ztkacxgfioclbkuebdzz.supabase.co:5432/postgres"
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
