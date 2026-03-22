import os
import logging
from urllib.parse import quote_plus
from cryptography.fernet import Fernet

from lazyllm.tools.sql import SqlManager


# 建议第一次用下面方式生成密钥并安全保存
# key = Fernet.generate_key()
# 保存到环境变量：FERNET_KEY
fernet_key = os.getenv('FERNET_KEY', Fernet.generate_key())
fernet = Fernet(fernet_key)


def encrypt(plaintext: str) -> str:
    try:
        return fernet.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logging.warning(f'Encryption error {e}, directly returning the input string')
        return plaintext


def decrypt(ciphertext: str) -> str:
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logging.warning(f'Decryption error {e}, directly returning the input string')
        return ciphertext


class EncryptSqlManager(SqlManager):
    def _gen_conn_url(self) -> str:
        if self._db_type == 'sqlite':
            conn_url = f"sqlite:///{self._db_name}{('?' + self._options_str) if self._options_str else ''}"
        else:
            driver = self.DB_DRIVER_MAP.get(self._db_type, '')
            password = quote_plus(decrypt(self._password))
            conn_url = (f"{self._db_type}{('+' + driver) if driver else ''}://{self._user}:{password}@{self._host}"
                        f":{self._port}/{self._db_name}{('?' + self._options_str) if self._options_str else ''}")
        return conn_url
