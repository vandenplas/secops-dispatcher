import hashlib
import hmac

SIGNATURE_HEADER = "X-Hub-Signature-256"
SIGNATURE_PREFIX = "sha256="


def expected_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    """Constant-time check of GitHub's X-Hub-Signature-256 header against the raw body."""
    if not secret or not signature:
        return False
    return hmac.compare_digest(expected_signature(secret, body), signature)
