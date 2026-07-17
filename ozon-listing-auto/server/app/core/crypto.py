from cryptography.fernet import Fernet
from app.core.config import settings

_fernet = Fernet(settings.fernet_key.encode())

def encrypt(plain: str) -> bytes:
    return _fernet.encrypt(plain.encode())

def decrypt(token: bytes) -> str:
    return _fernet.decrypt(bytes(token)).decode()
