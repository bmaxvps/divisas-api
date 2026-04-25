"""Base de datos PostgreSQL (Supabase)."""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from config import DATABASE_URL, PUNTOS, DIVISAS
import pytz

TZ = pytz.timezone("America/Caracas")

def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now(TZ).strftime("%Y-%m-%d")

def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def _fetchall(cur):
    return [dict(r) for r in cur.fetchall()]

def _fetchone(cur):
    r = cur.fetchone()
    return dict(r) if r else None


# ── INIT ──────────────────────────────────────────────────────────

def init_db():
    """Las tablas ya existen en Supabase. Solo inicializa saldos."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for punto in PUNTOS:
        for divisa in DIVISAS:
            cur.execute(
                "INSERT INTO saldos (punto, divisa, monto) VALUES (%s,%s,0.0) ON CONFLICT (punto,divisa) DO NOTHING",
                (punto, divisa)
            )
    conn.commit()
    cur.close()
    conn.close()


def init_usuarios():
    """Usuarios ya existen en Supabase. No-op."""
    pass


# ── USUARIOS ──────────────────────────────────────────────────────

def get_usuario(username: str) -> dict | None:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM usuarios_app WHERE LOWER(username)=LOWER(%s) AND activo=1", (username,)
    )
    row = _fetchone(cur)
    cur.close(); conn.close()
    return row


def get_usuarios() -> list:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id,username,rol,punto,nombre,activo FROM usuarios_app WHERE es_superuser=0")
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def crear_usuario(username: str, password_hash: str, rol: str, punto: str, nombre: str, es_superuser: int = 0):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO usuarios_app (username,password,rol,punto,nombre,es_superuser) VALUES (%s,%s,%s,%s,%s,%s)",
        (username, password_hash, rol, punto, nombre, es_superuser)
    )
    conn.commit()
    cur.close(); conn.close()


def eliminar_usuario(user_id: int):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("UPDATE usuarios_app SET activo=0 WHERE id=%s", (user_id,))
    conn.commit()
    cur.close(); conn.close()


def cambiar_password(user_id: int, nuevo_hash: str) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("UPDATE usuarios_app SET password=%s WHERE id=%s AND activo=1", (nuevo_hash, user_id))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


def cambiar_password_by_username(username: str, nuevo_hash: str) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("UPDATE usuarios_app SET password=%s WHERE LOWER(username)=LOWER(%s) AND activo=1", (nuevo_hash, username))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


# ── SALDOS ────────────────────────────────────────────────────────

def get_saldos_punto(punto: str) -> dict:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT divisa, monto FROM saldos WHERE punto=%s", (punto,))
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return {r["divisa"]: r["monto"] for r in rows}


def get_saldos_global() -> dict:
    conn   = get_conn()
    cur    = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT punto, divisa, monto FROM saldos")
    rows   = _fetchall(cur)
    cur.close(); conn.close()
    result = {}
    for r in rows:
        if r["punto"] not in result:
            result[r["punto"]] = {}
        result[r["punto"]][r["divisa"]] = r["monto"]
    return result


def actualizar_saldo(punto: str, divisa: str, delta: float):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE saldos SET monto = monto + %s WHERE punto=%s AND divisa=%s",
        (delta, punto, divisa)
    )
    conn.commit()
    cur.close(); conn.close()


# ── MOVIMIENTOS ───────────────────────────────────────────────────

def registrar_movimiento(punto, divisa, tipo, monto, descripcion, usuario_id, usuario_nom) -> int:
    fecha = now_str()
    delta = monto if tipo == "ingreso" else -monto
    conn  = get_conn()
    cur   = conn.cursor()
    cur.execute("""
        INSERT INTO movimientos (fecha,punto,divisa,tipo,monto,descripcion,usuario_id,usuario_nom)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (fecha, punto, divisa, tipo, monto, descripcion, usuario_id, usuario_nom))
    mov_id = cur.fetchone()[0]
    cur.execute(
        "UPDATE saldos SET monto = monto + %s WHERE punto=%s AND divisa=%s",
        (delta, punto, divisa)
    )
    conn.commit()
    cur.close(); conn.close()
    return mov_id


def get_movimientos(punto=None, limite=50, desde=None, hasta=None) -> list:
    conn   = get_conn()
    cur    = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query  = "SELECT * FROM movimientos WHERE 1=1"
    params = []
    if punto:
        query += " AND punto=%s"; params.append(punto)
    if desde:
        query += " AND fecha >= %s"; params.append(desde)
    if hasta:
        query += " AND fecha <= %s"; params.append(hasta + " 23:59:59")
    query += " ORDER BY fecha DESC LIMIT %s"
    params.append(limite)
    cur.execute(query, params)
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def editar_movimiento(mov_id: int, nuevo_monto: float, nueva_desc: str) -> bool:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM movimientos WHERE id=%s", (mov_id,))
    mov = _fetchone(cur)
    if not mov:
        cur.close(); conn.close()
        return False
    diff  = nuevo_monto - mov["monto"]
    delta = diff if mov["tipo"] == "ingreso" else -diff
    cur.execute("UPDATE movimientos SET monto=%s, descripcion=%s, editado=1 WHERE id=%s",
                (nuevo_monto, nueva_desc, mov_id))
    cur.execute("UPDATE saldos SET monto=monto+%s WHERE punto=%s AND divisa=%s",
                (delta, mov["punto"], mov["divisa"]))
    conn.commit()
    cur.close(); conn.close()
    return True


def eliminar_movimiento(mov_id: int) -> bool:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM movimientos WHERE id=%s", (mov_id,))
    mov = _fetchone(cur)
    if not mov:
        cur.close(); conn.close()
        return False
    delta = -mov["monto"] if mov["tipo"] == "ingreso" else mov["monto"]
    cur.execute("DELETE FROM movimientos WHERE id=%s", (mov_id,))
    cur.execute("UPDATE saldos SET monto=monto+%s WHERE punto=%s AND divisa=%s",
                (delta, mov["punto"], mov["divisa"]))
    conn.commit()
    cur.close(); conn.close()
    return True


# ── ORDENES ───────────────────────────────────────────────────────

def get_ordenes(punto=None, estado=None, fecha=None, desde=None, hasta=None, limite=500) -> list:
    conn   = get_conn()
    cur    = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query  = "SELECT * FROM ordenes WHERE 1=1"
    params = []
    if punto:
        query += " AND punto=%s"; params.append(punto)
    if estado:
        query += " AND estado=%s"; params.append(estado)
    if fecha:
        query += " AND DATE(fecha_creacion)=%s"; params.append(fecha)
    if desde:
        query += " AND (DATE(fecha_creacion)>=%s OR DATE(fecha_completado)>=%s)"
        params += [desde, desde]
    if hasta:
        query += " AND (DATE(fecha_creacion)<=%s OR DATE(fecha_completado)<=%s)"
        params += [hasta, hasta]
    query += f" ORDER BY fecha_creacion ASC LIMIT {int(limite)}"
    cur.execute(query, params)
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def get_orden_by_id(orden_id: int) -> dict | None:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM ordenes WHERE id=%s", (orden_id,))
    row = _fetchone(cur)
    cur.close(); conn.close()
    return row


def crear_orden(punto, tipo, cliente, divisa, monto_estimado, codigo="") -> int:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO ordenes (fecha_creacion,punto,tipo,cliente,divisa,monto_estimado,codigo)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (now_str(), punto, tipo, cliente, divisa, monto_estimado, codigo))
    orden_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return orden_id


def completar_orden(orden_id: int, monto_real: float, completado_por: str, completado_id: int) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE ordenes SET estado='completada', fecha_completado=%s, monto_real=%s,
        completado_por=%s, completado_id=%s WHERE id=%s AND estado='pendiente'
    """, (now_str(), monto_real, completado_por, completado_id, orden_id))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


def editar_orden(orden_id: int, cliente: str, monto_estimado: float, codigo: str, divisa: str = None) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    if divisa:
        cur.execute("""
            UPDATE ordenes SET cliente=%s,monto_estimado=%s,codigo=%s,divisa=%s
            WHERE id=%s AND estado='pendiente'
        """, (cliente, monto_estimado, codigo, divisa, orden_id))
    else:
        cur.execute("""
            UPDATE ordenes SET cliente=%s,monto_estimado=%s,codigo=%s
            WHERE id=%s AND estado='pendiente'
        """, (cliente, monto_estimado, codigo, orden_id))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


def editar_orden_ejecutada(orden_id: int, cliente: str, monto_real: float, tipo: str) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE ordenes SET cliente=%s, monto_real=%s, tipo=%s
        WHERE id=%s AND estado='completada'
    """, (cliente, monto_real, tipo, orden_id))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


def eliminar_orden(orden_id: int) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM ordenes WHERE id=%s", (orden_id,))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


# ── TASAS ─────────────────────────────────────────────────────────

def get_tasas_actuales() -> dict:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT par, tasa FROM tasas
        WHERE id IN (SELECT MAX(id) FROM tasas GROUP BY par)
    """)
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return {r["par"]: r["tasa"] for r in rows}


def set_tasa(par: str, tasa: float, usuario_nom: str = "") -> None:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO tasas (par,tasa,fecha,usuario_nom) VALUES (%s,%s,%s,%s)",
        (par, tasa, now_str(), usuario_nom)
    )
    conn.commit()
    cur.close(); conn.close()


# ── GASTOS ────────────────────────────────────────────────────────

def get_gastos(desde=None, hasta=None) -> list:
    conn   = get_conn()
    cur    = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query  = "SELECT * FROM gastos_personales WHERE 1=1"
    params = []
    if desde:
        query += " AND fecha >= %s"; params.append(desde)
    if hasta:
        query += " AND fecha <= %s"; params.append(hasta)
    query += " ORDER BY fecha DESC"
    cur.execute(query, params)
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def registrar_gasto(tipo, categoria, monto, descripcion, divisa="USD"):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO gastos_personales (fecha,tipo,categoria,monto,descripcion,divisa)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (today_str(), tipo, categoria, monto, descripcion, divisa))
    conn.commit()
    cur.close(); conn.close()


def eliminar_gasto(gasto_id: int) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM gastos_personales WHERE id=%s", (gasto_id,))
    ok = cur.rowcount > 0
    conn.commit()
    cur.close(); conn.close()
    return ok


# ── ALERTAS SALDO ─────────────────────────────────────────────────

def get_alertas_saldo() -> list:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM alertas_saldo")
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def set_alerta_saldo(punto: str, divisa: str, minimo: float, activo: int = 1):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO alertas_saldo (punto, divisa, minimo, activo)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (punto, divisa) DO UPDATE SET minimo=EXCLUDED.minimo, activo=EXCLUDED.activo
    """, (punto, divisa, minimo, activo))
    conn.commit()
    cur.close(); conn.close()


# ── CHAT ──────────────────────────────────────────────────────────

def get_mensajes_chat(punto: str, desde_id: int = 0, limite: int = 50) -> list:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, punto, remitente, rol_remit, contenido, imagen_b64, fecha, estado
        FROM chat_mensajes
        WHERE punto=%s AND id > %s
        ORDER BY id ASC LIMIT %s
    """, (punto, desde_id, limite))
    rows = _fetchall(cur)
    cur.close(); conn.close()
    return rows


def enviar_mensaje_chat(punto: str, remitente: str, rol_remit: str, contenido: str, imagen_b64: str = None) -> int:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO chat_mensajes (punto, remitente, rol_remit, contenido, imagen_b64, fecha, estado)
        VALUES (%s,%s,%s,%s,%s,%s,'enviado') RETURNING id
    """, (punto, remitente, rol_remit, contenido or '', imagen_b64, now_str()))
    msg_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return msg_id


def marcar_leido_chat(punto: str, username: str):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        UPDATE chat_mensajes SET estado='leido'
        WHERE punto=%s AND remitente != %s AND estado != 'leido'
    """, (punto, username))
    cur.execute("""
        UPDATE chat_mensajes SET estado='recibido'
        WHERE punto=%s AND remitente != %s AND estado='enviado'
    """, (punto, username))
    conn.commit()
    cur.close(); conn.close()


def limpiar_chat(punto: str):
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM chat_mensajes WHERE punto=%s", (punto,))
    conn.commit()
    cur.close(); conn.close()


def limpiar_chats_antiguos():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        DELETE FROM chat_mensajes
        WHERE fecha::timestamp < NOW() - INTERVAL '7 days'
    """)
    conn.commit()
    cur.close(); conn.close()


# ── RESET ─────────────────────────────────────────────────────────

def limpiar_datos_antiguos():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM movimientos WHERE fecha::timestamp < NOW() - INTERVAL '30 days'")
    cur.execute("""
        DELETE FROM ordenes
        WHERE fecha_creacion::timestamp < NOW() - INTERVAL '30 days'
        AND estado != 'pendiente'
    """)
    conn.commit()
    cur.close(); conn.close()


def inicio_del_dia() -> dict:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        DELETE FROM ordenes WHERE estado IN ('completada','cancelada')
        AND DATE(fecha_completado) < CURRENT_DATE
    """)
    r1 = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    limpiar_datos_antiguos()
    limpiar_chats_antiguos()
    return {"ordenes_ejecutadas_eliminadas": r1}


def resetear_todo() -> dict:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("DELETE FROM movimientos"); r1 = cur.rowcount
    cur.execute("DELETE FROM ordenes");    r2 = cur.rowcount
    cur.execute("DELETE FROM tasas")
    cur.execute("DELETE FROM alertas_config")
    cur.execute("DELETE FROM config_bot")
    cur.execute("DELETE FROM historial_actividad")
    cur.execute("DELETE FROM gastos_personales")
    cur.execute("DELETE FROM activos_pasivos")
    cur.execute("DELETE FROM chat_mensajes")
    cur.execute("UPDATE saldos SET monto=0.0")
    conn.commit()
    cur.close(); conn.close()
    return {"movimientos": r1, "ordenes": r2}
