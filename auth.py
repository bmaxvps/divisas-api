"""Autenticación JWT."""

from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_HORAS
import database as db

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def crear_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HORAS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_usuario_actual(token: str = Depends(oauth2)) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise exc
    except JWTError:
        raise exc

    usuario = db.get_usuario(username)
    if not usuario:
        raise exc
    return usuario


def solo_admin(usuario: dict = Depends(get_usuario_actual)) -> dict:
    if usuario["rol"] != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores")
    return usuario
