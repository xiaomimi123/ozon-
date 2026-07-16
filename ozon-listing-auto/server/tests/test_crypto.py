from app.core.crypto import encrypt, decrypt

def test_encrypt_roundtrip():
    token = encrypt("my-secret-key")
    assert isinstance(token, bytes)
    assert token != b"my-secret-key"
    assert decrypt(token) == "my-secret-key"
