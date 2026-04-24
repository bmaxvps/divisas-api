"""Base de datos SQLite — comparte el mismo archivo que el bot de Telegram."""

import sqlite3
import os
from datetime import datetime
from config import DB_PATH, PUNTOS, DIVISAS
import pytz

TZ = pytz.timezone("America/Caracas")

def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── USUARIOS (tabla nueva para la app) ───────────────────────────

def init_usuarios():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios_app (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            rol      TEXT NOT NULL DEFAULT 'operador',  -- 'admin' o 'operador'
            punto    TEXT,
            nombre   TEXT,
            activo   INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def get_usuario(username: str) -> dict | None:
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM usuarios_app WHERE username=? AND activo=1", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_usuarios() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT id,username,rol,punto,nombre,activo FROM usuarios_app").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def crear_usuario(username: str, password_hash: str, rol: str, punto: str, nombre: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO usuarios_app (username,password,rol,punto,nombre) VALUES (?,?,?,?,?)",
        (username, password_hash, rol, punto, nombre)
    )
    conn.commit()
    conn.close()


def eliminar_usuario(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE usuarios_app SET activo=0 WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


# ── SALDOS ────────────────────────────────────────────────────────

def get_saldos_punto(punto: str) -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT divisa, monto FROM saldos WHERE punto=?", (punto,)).fetchall()
    conn.close()
    return {r["divisa"]: r["monto"] for r in rows}


def get_saldos_global() -> dict:
    conn  = get_conn()
    rows  = conn.execute("SELECT punto, divisa, monto FROM saldos").fetchall()
    conn.close()
    result = {}
    for r in rows:
        if r["punto"] not in result:
            result[r["punto"]] = {}
        result[r["punto"]][r["divisa"]] = r["monto"]
    return result


def actualizar_saldo(punto: str, divisa: str, delta: float):
    conn = get_conn()
    conn.execute(
        "UPDATE saldos SET monto = monto + ? WHERE punto=? AND divisa=?",
        (delta, punto, divisa)
    )
    conn.commit()
    conn.close()


# ── MOVIMIENTOS ───────────────────────────────────────────────────

def registrar_movimiento(punto, divisa, tipo, monto, descripcion, usuario_id, usuario_nom) -> int:
    fecha = now_str()
    delta = monto if tipo == "ingreso" else -monto
    conn  = get_conn()
    cur   = conn.execute("""
        INSERT INTO movimientos (fecha,punto,divisa,tipo,monto,descripcion,usuario_id,usuario_nom)
        VALUES (?,?,?,?,?,?,?,?)
    """, (fecha, punto, divisa, tipo, monto, descripcion, usuario_id, usuario_nom))
    mov_id = cur.lastrowid
    conn.execute(
        "UPDATE saldos SET monto = monto + ? WHERE punto=? AND divisa=?",
        (delta, punto, divisa)
    )
    conn.commit()
    conn.close()
    return mov_id


def get_movimientos(punto=None, limite=50, desde=None, hasta=None) -> list:
    conn   = get_conn()
    query  = "SELECT * FROM movimientos WHERE 1=1"
    params = []
    if punto:
        query += " AND punto=?"
        params.append(punto)
    if desde:
        query += " AND fecha >= ?"
        params.append(desde)
    if hasta:
        query += " AND fecha <= ?"
        params.append(hasta + " 23:59:59")
    query += " ORDER BY fecha DESC LIMIT ?"
    params.append(limite)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def editar_movimiento(mov_id: int, nuevo_monto: float, nueva_desc: str) -> bool:
    conn = get_conn()
    mov  = conn.execute("SELECT * FROM movimientos WHERE id=?", (mov_id,)).fetchone()
    if not mov:
        conn.close()
        return False
    diff  = nuevo_monto - mov["monto"]
    delta = diff if mov["tipo"] == "ingreso" else -diff
    conn.execute("UPDATE movimientos SET monto=?, descripcion=?, editado=1 WHERE id=?",
                 (nuevo_monto, nueva_desc, mov_id))
    conn.execute("UPDATE saldos SET monto=monto+? WHERE punto=? AND divisa=?",
                 (delta, mov["punto"], mov["divisa"]))
    conn.commit()
    conn.close()
    return True


def eliminar_movimiento(mov_id: int) -> bool:
    conn = get_conn()
    mov  = conn.execute("SELECT * FROM movimientos WHERE id=?", (mov_id,)).fetchone()
    if not mov:
        conn.close()
        return False
    delta = -mov["monto"] if mov["tipo"] == "ingreso" else mov["monto"]
    conn.execute("DELETE FROM movimientos WHERE id=?", (mov_id,))
    conn.execute("UPDATE saldos SET monto=monto+? WHERE punto=? AND divisa=?",
                 (delta, mov["punto"], mov["divisa"]))
    conn.commit()
    conn.close()
    return True


# ── ORDENES ───────────────────────────────────────────────────────

def get_ordenes(punto=None, estado=None, fecha=None) -> list:
    conn   = get_conn()
    query  = "SELECT * FROM ordenes WHERE 1=1"
    params = []
    if punto:
        query += " AND punto=?"
        params.append(punto)
    if estado:
        query += " AND estado=?"
        params.append(estado)
    if fecha:
        query += " AND DATE(fecha_creacion)=?"
        params.append(fecha)
    query += " ORDER BY fecha_creacion ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orden_by_id(orden_id: int) -> dict | None:
    conn = get_conn()
    row  = conn.execute("SELECT * FROM ordenes WHERE id=?", (orden_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def crear_orden(punto, tipo, cliente, divisa, monto_estimado, codigo="") -> int:
    conn = get_conn()
    cur  = conn.execute("""
        INSERT INTO ordenes (fecha_creacion,punto,tipo,cliente,divisa,monto_estimado,codigo)
        VALUES (?,?,?,?,?,?,?)
    """, (now_str(), punto, tipo, cliente, divisa, monto_estimado, codigo))
    orden_id = cur.lastrowid
    conn.commit()
    conn.close()
    return orden_id


def completar_orden(orden_id: int, monto_real: float, completado_por: str, completado_id: int) -> bool:
    conn = get_conn()
    cur  = conn.execute("""
        UPDATE ordenes SET estado='completada', fecha_completado=?, monto_real=?,
        completado_por=?, completado_id=? WHERE id=? AND estado='pendiente'
    """, (now_str(), monto_real, completado_por, completado_id, orden_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def editar_orden(orden_id: int, cliente: str, monto_estimado: float, codigo: str, divisa: str = None) -> bool:
    conn = get_conn()
    if divisa:
        cur = conn.execute("""
            UPDATE ordenes SET cliente=?,monto_estimado=?,codigo=?,divisa=?
            WHERE id=? AND estado='pendiente'
        """, (cliente, monto_estimado, codigo, divisa, orden_id))
    else:
        cur = conn.execute("""
            UPDATE ordenes SET cliente=?,monto_estimado=?,codigo=?
            WHERE id=? AND estado='pendiente'
        """, (cliente, monto_estimado, codigo, orden_id))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def eliminar_orden(orden_id: int) -> bool:
    conn = get_conn()
    cur  = conn.execute("DELETE FROM ordenes WHERE id=? AND estado='pendiente'", (orden_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ── TASAS ─────────────────────────────────────────────────────────

def get_tasas_actuales() -> dict:
    conn = get_conn()
    rows = conn.execute("""
        SELECT par, tasa FROM tasas
        WHERE id IN (SELECT MAX(id) FROM tasas GROUP BY par)
    """).fetchall()
    conn.close()
    return {r["par"]: r["tasa"] for r in rows}


def set_tasa(par: str, tasa: float, usuario_nom: str = "") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO tasas (par,tasa,fecha,usuario_nom) VALUES (?,?,?,?)",
        (par, tasa, now_str(), usuario_nom)
    )
    conn.commit()
    conn.close()


# ── GASTOS ────────────────────────────────────────────────────────

def get_gastos(desde=None, hasta=None) -> list:
    conn   = get_conn()
    query  = "SELECT * FROM gastos_personales WHERE 1=1"
    params = []
    if desde:
        query += " AND fecha >= ?"
        params.append(desde)
    if hasta:
        query += " AND fecha <= ?"
        params.append(hasta)
    query += " ORDER BY fecha DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def registrar_gasto(tipo, categoria, monto, descripcion, divisa="USD"):
    conn = get_conn()
    conn.execute("""
        INSERT INTO gastos_personales (fecha,tipo,categoria,monto,descripcion,divisa)
        VALUES (?,?,?,?,?,?)
    """, (today_str(), tipo, categoria, monto, descripcion, divisa))
    conn.commit()
    conn.close()


def eliminar_gasto(gasto_id: int) -> bool:
    conn = get_conn()
    cur  = conn.execute("DELETE FROM gastos_personales WHERE id=?", (gasto_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ── RESET ─────────────────────────────────────────────────────────

def inicio_del_dia() -> dict:
    conn = get_conn()
    r1   = conn.execute("""
        DELETE FROM ordenes WHERE estado IN ('completada','cancelada')
        AND DATE(fecha_completado) < DATE('now','localtime')
    """).rowcount
    conn.commit()
    conn.close()
    return {"ordenes_ejecutadas_eliminadas": r1}


def resetear_todo() -> dict:
    conn = get_conn()
    r1 = conn.execute("DELETE FROM movimientos").rowcount
    r2 = conn.execute("DELETE FROM ordenes").rowcount
    conn.execute("DELETE FROM tasas")
    conn.execute("DELETE FROM alertas_config")
    conn.execute("DELETE FROM config_bot")
    conn.execute("DELETE FROM historial_actividad")
    conn.execute("DELETE FROM gastos_personales")
    conn.execute("DELETE FROM activos_pasivos")
    conn.execute("UPDATE saldos SET monto=0.0")
    conn.commit()
    conn.close()
    return {"movimientos": r1, "ordenes": r2}
