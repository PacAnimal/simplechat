import logging
import os
import secrets

logger = logging.getLogger(__name__)

_KEY_FILENAME = "jwt_secret.key"
_DEFAULT_INSECURE = "simplechat-dev-secret-change-in-production"


def resolve(data_dir: str, configured: str) -> str:
    """Return the JWT secret — from env var, persisted key file, or newly generated."""
    if configured and configured != _DEFAULT_INSECURE:
        return configured
    key_file = os.path.join(data_dir, _KEY_FILENAME)
    if os.path.exists(key_file):
        with open(key_file) as f:
            secret = f.read().strip()
        if len(secret) >= 32:
            return secret
    secret = secrets.token_hex(64)
    os.makedirs(data_dir, exist_ok=True)
    with open(key_file, "w") as f:
        f.write(secret)
    logger.info("Generated new JWT secret at %s", key_file)
    return secret
