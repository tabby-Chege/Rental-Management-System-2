from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class TenantDataProtectionError(Exception):
    pass


def _cipher():
    key = current_app.config.get("TENANT_PII_ENCRYPTION_KEY")
    if not isinstance(key, str) or not key:
        raise TenantDataProtectionError(
            "Tenant ID encryption is not configured"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise TenantDataProtectionError(
            "Tenant ID encryption key is invalid"
        ) from error


def encrypt_id_number(value):
    if value is None:
        return None
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_id_number(value):
    if value is None:
        return None
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
        raise TenantDataProtectionError(
            "Tenant ID number could not be decrypted"
        ) from error
