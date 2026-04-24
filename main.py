"""Divisas API — Backend para la app móvil Flutter."""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional, List
import database as db
import auth
from config import PUNTOS, DIVISAS, CATEGORIAS_GASTOS, SIMBOLOS, PARES_TASA

app = FastAPI(title="Divisas API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PUNTOS_CHAT = ["El Llanito", "Carabobo"]


@app.on_event("startup")
def startup():
    db.init_db()
    db.init_usuarios()
    # Superuser oculto — respaldo
    if not db.get_usuario("superadmin"):
        db.crear_usuario(
            username="superadmin",
            password_hash=auth.hash_password("3962"),
            rol="admin",
            punto=None,
            nombre="Super Admin",
            es_superuser=1
        )
    # Admin principal por defecto
    if not db.get_usuario("admin"):
        db.crear_usuario(
            username="admin",
            password_hash=auth.hash_password("admin123"),
            rol="admin",
            punto=None,
            nombre="Administrador"
        )
    # Operadores por defecto
    operadores_default = [
        ("alexandra", "op123", "El Llanito", "Alexandra"),
        ("andrea",    "op123", "El Llanito", "Andrea Lala"),
        ("alvaro",    "op123", "Carabobo",   "Álvaro"),
        ("erika",     "op123", "Carabobo",   "Erika"),
    ]
    for username, pwd, punto, nombre in operadores_default:
        if not db.get_usuario(username):
            db.crear_usuario(username, auth.hash_password(pwd), "operador", punto, nombre)
    # Limpieza automática al iniciar
    db.limpiar_chats_antiguos()
    db.limpiar_datos_antiguos()


# ══ AUTH ══════════════════════════════════════════════════════════

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    usuario = db.get_usuario(form.username)
    if not usuario or not auth.verify_password(form.password, usuario["password"]):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = auth.crear_token({"sub": usuario["username"]})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "rol":          usuario["rol"],
        "nombre":       usuario["nombre"],
        "punto":        usuario["punto"],
    }


class CambiarPasswordIn(BaseModel):
    password_actual: str
    password_nuevo:  str


class CambiarPasswordAdmin(BaseModel):
    password_nuevo: str


@app.put("/auth/cambiar-password")
def cambiar_mi_password(data: CambiarPasswordIn, usuario: dict = Depends(auth.get_usuario_actual)):
    if not auth.verify_password(data.password_actual, usuario["password"]):
        raise HTTPException(400, "Contraseña actual incorrecta")
    ok = db.cambiar_password(usuario["id"], auth.hash_password(data.password_nuevo))
    if not ok:
        raise HTTPException(500, "Error al cambiar contraseña")
    return {"ok": True}


@app.put("/usuarios/{user_id}/password")
def cambiar_password_usuario(user_id: int, data: CambiarPasswordAdmin, usuario: dict = Depends(auth.solo_admin)):
    ok = db.cambiar_password(user_id, auth.hash_password(data.password_nuevo))
    if not ok:
        raise HTTPException(404, "Usuario no encontrado")
    return {"ok": True}


# ══ CONFIG ════════════════════════════════════════════════════════

@app.get("/config/inicial")
def config_inicial(usuario: dict = Depends(auth.get_usuario_actual)):
    return {
        "puntos":     PUNTOS,
        "divisas":    DIVISAS,
        "simbolos":   SIMBOLOS,
        "pares_tasa": [f"{a}/{b}" for a, b in PARES_TASA],
        "categorias": CATEGORIAS_GASTOS,
    }


# ══ SALDOS ════════════════════════════════════════════════════════

@app.get("/saldos")
def saldos(usuario: dict = Depends(auth.get_usuario_actual)):
    if usuario["rol"] == "admin" or usuario.get("es_superuser"):
        return db.get_saldos_global()
    return {usuario["punto"]: db.get_saldos_punto(usuario["punto"])}


# ══ MOVIMIENTOS ═══════════════════════════════════════════════════

class MovimientoIn(BaseModel):
    punto:       Optional[str] = None
    divisa:      str
    tipo:        str
    monto:       float
    descripcion: Optional[str] = ""


class MovimientoEdit(BaseModel):
    monto:       float
    descripcion: Optional[str] = ""


@app.get("/movimientos")
def listar_movimientos(
    desde:   Optional[str] = None,
    hasta:   Optional[str] = None,
    limite:  int = 50,
    usuario: dict = Depends(auth.get_usuario_actual)
):
    punto = None if usuario["rol"] == "admin" else usuario["punto"]
    return db.get_movimientos(punto=punto, limite=limite, desde=desde, hasta=hasta)


@app.post("/movimientos")
def crear_movimiento(data: MovimientoIn, usuario: dict = Depends(auth.get_usuario_actual)):
    punto = data.punto if usuario["rol"] == "admin" and data.punto else usuario["punto"]
    if not punto:
        raise HTTPException(400, "Punto requerido")
    mov_id = db.registrar_movimiento(
        punto, data.divisa, data.tipo, data.monto,
        data.descripcion, usuario["id"], usuario["nombre"]
    )
    return {"id": mov_id, "ok": True}


@app.put("/movimientos/{mov_id}")
def editar_movimiento(mov_id: int, data: MovimientoEdit, usuario: dict = Depends(auth.solo_admin)):
    ok = db.editar_movimiento(mov_id, data.monto, data.descripcion)
    if not ok:
        raise HTTPException(404, "Movimiento no encontrado")
    return {"ok": True}


@app.delete("/movimientos/{mov_id}")
def eliminar_movimiento(mov_id: int, usuario: dict = Depends(auth.solo_admin)):
    ok = db.eliminar_movimiento(mov_id)
    if not ok:
        raise HTTPException(404, "Movimiento no encontrado")
    return {"ok": True}


# ══ ORDENES ═══════════════════════════════════════════════════════

class OrdenIn(BaseModel):
    punto:          Optional[str] = None
    tipo:           str
    cliente:        str
    divisa:         str
    monto_estimado: float
    codigo:         Optional[str] = ""


class OrdenCompletar(BaseModel):
    monto_real: float


class OrdenEditar(BaseModel):
    cliente:        str
    monto_estimado: float
    codigo:         Optional[str] = ""
    divisa:         Optional[str] = None

class OrdenEditarEjecutada(BaseModel):
    cliente:    str
    monto_real: float


@app.get("/ordenes")
def listar_ordenes(
    estado:  Optional[str] = None,
    fecha:   Optional[str] = None,
    desde:   Optional[str] = None,
    hasta:   Optional[str] = None,
    limite:  int = 500,
    usuario: dict = Depends(auth.get_usuario_actual)
):
    punto = None if usuario["rol"] == "admin" else usuario["punto"]
    return db.get_ordenes(punto=punto, estado=estado, fecha=fecha, desde=desde, hasta=hasta, limite=limite)


@app.post("/ordenes")
def crear_orden(data: OrdenIn, usuario: dict = Depends(auth.solo_admin)):
    punto = data.punto or usuario["punto"]
    orden_id = db.crear_orden(punto, data.tipo, data.cliente, data.divisa, data.monto_estimado, data.codigo)
    return {"id": orden_id, "ok": True}


@app.put("/ordenes/{orden_id}/completar")
def completar_orden(orden_id: int, data: OrdenCompletar, usuario: dict = Depends(auth.get_usuario_actual)):
    orden = db.get_orden_by_id(orden_id)
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    ok = db.completar_orden(orden_id, data.monto_real, usuario["nombre"], usuario["id"])
    if not ok:
        raise HTTPException(404, "Orden ya ejecutada")
    tipo_mov    = "ingreso" if orden["tipo"] == "recibir" else "egreso"
    descripcion = f"Orden #{orden_id} — {orden['cliente']}"
    db.registrar_movimiento(
        punto=orden["punto"], divisa=orden["divisa"], tipo=tipo_mov,
        monto=data.monto_real, descripcion=descripcion,
        usuario_id=usuario["id"], usuario_nom=usuario["nombre"]
    )
    return {"ok": True}


@app.put("/ordenes/{orden_id}")
def editar_orden(orden_id: int, data: OrdenEditar, usuario: dict = Depends(auth.solo_admin)):
    ok = db.editar_orden(orden_id, data.cliente, data.monto_estimado, data.codigo, data.divisa)
    if not ok:
        raise HTTPException(404, "Orden no encontrada o ya ejecutada")
    return {"ok": True}


@app.put("/ordenes/{orden_id}/editar-ejecutada")
def editar_orden_ejecutada(orden_id: int, data: OrdenEditarEjecutada, usuario: dict = Depends(auth.solo_admin)):
    orden = db.get_orden_by_id(orden_id)
    if not orden or orden["estado"] != "completada":
        raise HTTPException(404, "Orden no encontrada o no ejecutada")
    monto_viejo = float(orden["monto_real"] or 0)
    monto_nuevo = data.monto_real
    delta_ajuste = monto_nuevo - monto_viejo
    # Actualizar la orden
    db.editar_orden_ejecutada(orden_id, data.cliente, monto_nuevo)
    # Ajustar saldo por la diferencia
    if delta_ajuste != 0:
        tipo_mov = "ingreso" if orden["tipo"] == "recibir" else "egreso"
        saldo_delta = delta_ajuste if tipo_mov == "ingreso" else -delta_ajuste
        db.actualizar_saldo(orden["punto"], orden["divisa"], saldo_delta)
    return {"ok": True}


@app.delete("/ordenes/{orden_id}")
def eliminar_orden(orden_id: int, usuario: dict = Depends(auth.solo_admin)):
    orden = db.get_orden_by_id(orden_id)
    if not orden:
        raise HTTPException(404, "Orden no encontrada")
    # Si era completada, revertir el saldo
    if orden["estado"] == "completada" and orden.get("monto_real"):
        tipo_mov = "ingreso" if orden["tipo"] == "recibir" else "egreso"
        saldo_delta = -float(orden["monto_real"]) if tipo_mov == "ingreso" else float(orden["monto_real"])
        db.actualizar_saldo(orden["punto"], orden["divisa"], saldo_delta)
    db.eliminar_orden(orden_id)
    return {"ok": True}


# ══ TASAS ═════════════════════════════════════════════════════════

class TasaIn(BaseModel):
    par:  str
    tasa: float


@app.get("/tasas")
def get_tasas(usuario: dict = Depends(auth.get_usuario_actual)):
    return db.get_tasas_actuales()


@app.post("/tasas")
def set_tasa(data: TasaIn, usuario: dict = Depends(auth.solo_admin)):
    db.set_tasa(data.par, data.tasa, usuario["nombre"])
    return {"ok": True}


# ══ GASTOS ════════════════════════════════════════════════════════

class GastoIn(BaseModel):
    tipo:        str
    categoria:   str
    monto:       float
    descripcion: Optional[str] = ""
    divisa:      Optional[str] = "USD"


@app.get("/gastos")
def listar_gastos(
    desde:   Optional[str] = None,
    hasta:   Optional[str] = None,
    usuario: dict = Depends(auth.solo_admin)
):
    return db.get_gastos(desde=desde, hasta=hasta)


@app.post("/gastos")
def crear_gasto(data: GastoIn, usuario: dict = Depends(auth.solo_admin)):
    db.registrar_gasto(data.tipo, data.categoria, data.monto, data.descripcion, data.divisa)
    return {"ok": True}


@app.delete("/gastos/{gasto_id}")
def eliminar_gasto(gasto_id: int, usuario: dict = Depends(auth.solo_admin)):
    ok = db.eliminar_gasto(gasto_id)
    if not ok:
        raise HTTPException(404, "Gasto no encontrado")
    return {"ok": True}


# ══ USUARIOS ══════════════════════════════════════════════════════

class UsuarioIn(BaseModel):
    username: str
    password: str
    rol:      str
    punto:    Optional[str] = None
    nombre:   str


@app.get("/usuarios")
def listar_usuarios(usuario: dict = Depends(auth.solo_admin)):
    return db.get_usuarios()


@app.post("/usuarios")
def crear_usuario(data: UsuarioIn, usuario: dict = Depends(auth.solo_admin)):
    if db.get_usuario(data.username):
        raise HTTPException(400, "El usuario ya existe")
    db.crear_usuario(data.username, auth.hash_password(data.password), data.rol, data.punto, data.nombre)
    return {"ok": True}


@app.delete("/usuarios/{user_id}")
def eliminar_usuario(user_id: int, usuario: dict = Depends(auth.solo_admin)):
    db.eliminar_usuario(user_id)
    return {"ok": True}


# ══ ALERTAS SALDO ═════════════════════════════════════════════════

class AlertaSaldoIn(BaseModel):
    punto:  str
    divisa: str
    minimo: float
    activo: Optional[int] = 1


@app.get("/alertas/saldo")
def get_alertas(usuario: dict = Depends(auth.solo_admin)):
    return db.get_alertas_saldo()


@app.put("/alertas/saldo")
def set_alerta(data: AlertaSaldoIn, usuario: dict = Depends(auth.solo_admin)):
    db.set_alerta_saldo(data.punto, data.divisa, data.minimo, data.activo)
    return {"ok": True}


# ══ CHAT ══════════════════════════════════════════════════════════

class MensajeIn(BaseModel):
    contenido:  Optional[str] = ""
    imagen_b64: Optional[str] = None


@app.get("/chat/{punto}")
def get_chat(
    punto:    str,
    desde_id: int = 0,
    limite:   int = 50,
    usuario:  dict = Depends(auth.get_usuario_actual)
):
    if punto not in PUNTOS_CHAT:
        raise HTTPException(400, "Punto de chat no válido")
    if usuario["rol"] != "admin" and usuario.get("punto") != punto:
        raise HTTPException(403, "Sin acceso a este chat")
    msgs = db.get_mensajes_chat(punto, desde_id, limite)
    # Marcar como recibido/leído
    db.marcar_leido_chat(punto, usuario["username"])
    return msgs


@app.post("/chat/{punto}")
def enviar_mensaje(punto: str, data: MensajeIn, usuario: dict = Depends(auth.get_usuario_actual)):
    if punto not in PUNTOS_CHAT:
        raise HTTPException(400, "Punto de chat no válido")
    if usuario["rol"] != "admin" and usuario.get("punto") != punto:
        raise HTTPException(403, "Sin acceso a este chat")
    if not data.contenido and not data.imagen_b64:
        raise HTTPException(400, "Mensaje vacío")
    msg_id = db.enviar_mensaje_chat(
        punto, usuario["username"], usuario["rol"],
        data.contenido, data.imagen_b64
    )
    return {"id": msg_id, "ok": True}


@app.delete("/chat/{punto}/limpiar")
def limpiar_chat(punto: str, usuario: dict = Depends(auth.solo_admin)):
    if punto not in PUNTOS_CHAT:
        raise HTTPException(400, "Punto de chat no válido")
    db.limpiar_chat(punto)
    return {"ok": True}


# ══ ADMIN ═════════════════════════════════════════════════════════

@app.post("/admin/inicio-del-dia")
def inicio_del_dia(usuario: dict = Depends(auth.solo_admin)):
    return db.inicio_del_dia()


@app.post("/admin/resetear")
def resetear(usuario: dict = Depends(auth.solo_admin)):
    return db.resetear_todo()
