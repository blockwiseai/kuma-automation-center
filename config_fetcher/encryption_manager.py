import os
import sys
from base64 import b64encode, b64decode
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESCCM, AESSIV

class EncryptionManager:
    def __init__(self):
        master_key = os.getenv('ENCRYPTION_MASTER_KEY')
        if not master_key:
            raise Exception("No ENCRYPTION_MASTER_KEY set")
        
        # Derive a key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 32 bytes = 256 bits
            salt=b'some_random_salt',
            iterations=480000,
        )
        self.key = kdf.derive(b64decode(master_key))

    def encrypt(self, data: str) -> str:
        if not data:
            return ''
        
        # AES-SIV for deterministic encryption
        siv = AESSIV(self.key)
        encrypted_data = siv.encrypt(data.encode(), associated_data=None)
        return b64encode(encrypted_data).decode()

    def decrypt(self, encrypted_data: str) -> str:
        if not encrypted_data:
            return ''
        
        siv = AESSIV(self.key)
        decrypted_data = siv.decrypt(b64decode(encrypted_data), associated_data=None)
        return decrypted_data.decode()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("The script requires exactly 1 argument")
        exit(1)
    encryptionManager = EncryptionManager()
    print(encryptionManager.decrypt(sys.argv[1]))
