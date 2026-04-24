"""Divisas API — Backend para la app móvil Flutter."""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional
import database as db
import auth
from config import PUNTOS, DIVISAS, CATEGORIAS_GASTOS, SIMBOLOS, PARES_TASA

app = FastAPI(title="Divisas API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()
    db.init_usuarios()
    # Crear admin por defecto si no existe
    if not db.get_usuario("admin"):
        db.crear_usuario(
            username="admin",
            password_hash=auth.hash_password("admin123"),
            rol="admin",
            punto=None,
            nombre="Administrador"
        )
    # Crear operadores por defecto
    operadores_default = [
        ("alexandra",  "op123", "El Llanito", "Alexandra"),
        ("andrea",     "op123", "El Llanito", "Andrea Lala"),
        ("alvaro",     "op123", "Carabobo",   "Álvaro"),
        ("erika",      "op123", "Carabobo",   "Erika"),
    ]
    for username, pwd, punto, nombre in operadores_default:
        if not db.get_usuario(username):
            db.crear_usuario(username, auth.hash_password(pwd), "operador", punto, nombre)


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


# ══ CONFIG ════════════════════════════════════════════════════════

@app.get("/config/inicial")
def config_inicial(usuario: dict = Depends(auth.get_usuario_actual)):
    return {
        "puntos":      PUNTOS,
        "divisas":     DIVISAS,
        "simbolos":    SIMBOLOS,
        "pares_tasa":  [f"{a}/{b}" for a, b in PARES_TASA],
        "categorias":  CATEGORIAS_GASTOS,
    }


# ══ SALDOS ════════════════════════════════════════════════════════

@app.get("/saldos")
def saldos(usuario: dict = Depends(auth.get_usuario_actual)):
    if usuario["rol"] == "admin":
        return db.get_saldos_global()
    return {usuario["punto"]: db.get_saldos_punto(usuario["punto"])}


# ══ MOVIMIENTOS ═══════════════════════════════════════════════════

class MovimientoIn(BaseModel):
    punto:      Optional[str] = None
    divisa:     str
    tipo:       str   # 'ingreso' o 'egreso'
    monto:      float
    descripcion: Optional[str] = ""


class MovimientoEdit(BaseModel):
    monto:      float
    descripcion: Optional[str] = ""


@app.get("/movimientos")
def listar_movimientos(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    limite: int = 50,
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
    tipo:           str   # 'recibir' o 'entregar'
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


@app.get("/ordenes")
def listar_ordenes(
    estado: Optional[str] = None,
    fecha:  Optional[str] = None,
    usuario: dict = Depends(auth.get_usuario_actual)
):
    punto = None if usuario["rol"] == "admin" else usuario["punto"]
    return db.get_ordenes(punto=punto, estado=estado, fecha=fecha)


@app.post("/ordenes")
def crear_orden(data: OrdenIn, usuario: dict = Depends(auth.solo_admin)):
    punto = data.punto or usuario["punto"]
    orden_id = db.crear_orden(punto, data.tipo, data.cliente, data.divisa, data.monto_estimado, data.codigo)
    return {"id": orden_id, "ok": True}


@app.put("/ordenes/{orden_id}/completar")
def completar_orden(orden_id: int, data: OrdenCompletar, usuario: dict = Depends(auth.get_usuario_actual)):
    ok = db.completar_orden(orden_id, data.monto_real, usuario["nombre"], usuario["id"])
    if not ok:
        raise HTTPException(404, "Orden no encontrada o ya ejecutada")
    return {"ok": True}


@app.put("/ordenes/{orden_id}")
def editar_orden(orden_id: int, data: OrdenEditar, usuario: dict = Depends(auth.solo_admin)):
    ok = db.editar_orden(orden_id, data.cliente, data.monto_estimado, data.codigo, data.divisa)
    if not ok:
        raise HTTPException(404, "Orden no encontrada o ya ejecutada")
    return {"ok": True}


@app.delete("/ordenes/{orden_id}")
def eliminar_orden(orden_id: int, usuario: dict = Depends(auth.solo_admin)):
    ok = db.eliminar_orden(orden_id)
    if not ok:
        raise HTTPException(404, "Orden no encontrada o ya ejecutada")
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
    tipo:        str   # 'ingreso' o 'gasto'
    categoria:   str
    monto:       float
    descripcion: Optional[str] = ""
    divisa:      Optional[str] = "USD"


@app.get("/gastos")
def listar_gastos(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
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


# ══ ADMIN — USUARIOS ══════════════════════════════════════════════

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


# ══ ADMIN — RESET ═════════════════════════════════════════════════

@app.post("/admin/inicio-del-dia")
def inicio_del_dia(usuario: dict = Depends(auth.solo_admin)):
    return db.inicio_del_dia()


@app.post("/admin/resetear")
def resetear(usuario: dict = Depends(auth.solo_admin)):
    return db.resetear_todo()
