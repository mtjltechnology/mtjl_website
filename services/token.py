import base64
import uuid
from datetime import datetime, timedelta

import jwt

from config import settings


def generate_pilotqa_token(email: str, plan: str) -> str:
    private_key_pem = base64.b64decode(settings.pilotqa_jwt_private_key).decode()
    payload = {
        "userId": email,
        "plan": plan.lower(),
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=365),
        "iss": "pilotqa.token.server",
        "aud": f"pilotqa.{plan.lower()}",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")
