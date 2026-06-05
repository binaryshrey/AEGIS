"""
Agent Auth wrapper for the Battleship competition server.

Three key sources (checked in order):
  1. ENV VARS: AGENT_AUTH_PRIVATE_KEY (JWK JSON) + AGENT_AUTH_AGENT_ID
     → For Render/server deployments. Set once, works forever.
  2. FILESYSTEM: ~/.agent-auth/agents/*.json
     → For laptop use. Written by auth-agent CLI after connect().
  3. CLI FALLBACK: shells out to auth-agent binary (~240ms per call)
     → Last resort if key can't be loaded directly.

Sources 1 and 2 use Python-native signing (~0.2ms per token).

First run:  call connect() to get a verification URL, approve once.
Every run:  call sign_jwt() to mint a fresh single-use JWT per request.
"""
import glob
import json
import os
import shutil
import subprocess
import time
import uuid

PROD_SERVER = "https://intern-battleship-game-server.vercel.app"
AGENT_ID_PATH = os.path.join("data", "agent_id.txt")
AUTH_DIR = os.path.expanduser("~/.agent-auth")

ALL_CAPABILITIES = [
    "getCompetitionRules",
    "createAttempt",
    "getCurrentAttempt",
    "placeShips",
    "submitShot",
    "abandonAttempt",
]

# ── Cached state ──────────────────────────────────────────────────────────────

_auth_binary: list[str] | None = None
_native_signer: object | None = None  # _NativeSigner instance
_native_tried: bool = False


# ── Python-native JWT signing ─────────────────────────────────────────────────

class _NativeSigner:
    """
    Signs agent JWTs using PyJWT + cryptography, bypassing the CLI.
    Reads the Ed25519/EC private key from ~/.agent-auth/agents/.
    ~1ms per sign vs ~240ms for subprocess.
    """
    def __init__(self, agent_id: str, private_key, algorithm: str,
                 kid: str, audience: str):
        self.agent_id = agent_id
        self.private_key = private_key
        self.algorithm = algorithm
        self.kid = kid
        self.audience = audience

    def sign(self, capabilities: list[str]) -> str:
        import jwt as pyjwt

        now = int(time.time())
        payload = {
            "sub": self.agent_id,
            "aud": self.audience,
            "iat": now,
            "exp": now + 60,
            "jti": str(uuid.uuid4()),
            "capabilities": capabilities,
        }
        headers = {
            "typ": "agent+jwt",
            "kid": self.kid,
        }
        return pyjwt.encode(payload, self.private_key, algorithm=self.algorithm,
                            headers=headers)


def _try_load_native_signer(agent_id: str) -> _NativeSigner | None:
    """
    Attempt to load the private key and create a native signer.
    Checks (in order):
      1. AGENT_AUTH_PRIVATE_KEY env var (JWK JSON string)
      2. ~/.agent-auth/agents/*.json files
    Returns None if the key can't be found or parsed.
    """
    try:
        import jwt as pyjwt
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
    except ImportError:
        return None

    # ── Source 1: Environment variable ────────────────────────────────────────
    env_key = os.environ.get("AGENT_AUTH_PRIVATE_KEY")
    if env_key:
        try:
            key_data = json.loads(env_key)
            signer = _build_signer_from_jwk(agent_id, key_data)
            if signer:
                return signer
        except Exception:
            pass

    # ── Source 2: Filesystem (~/.agent-auth) ──────────────────────────────────
    agents_dir = os.path.join(AUTH_DIR, "agents")
    if not os.path.isdir(agents_dir):
        return None

    # Find the agent's JSON file
    for fpath in glob.glob(os.path.join(agents_dir, "*.json")):
        try:
            data = json.loads(open(fpath).read())
        except Exception:
            continue

        # The file may store agent data at top level or nested
        # Look for our agent_id and a private key
        file_agent_id = data.get("agentId") or data.get("agent_id") or data.get("id")
        if file_agent_id and file_agent_id != agent_id:
            continue

        # Find private key (JWK format)
        key_data = (data.get("privateKey") or data.get("private_key")
                    or data.get("keyPair", {}).get("privateKey")
                    or data.get("keys", {}).get("privateKey"))

        if not key_data:
            # Try the whole object as a JWK
            if "kty" in data:
                key_data = data
            else:
                continue

        if isinstance(key_data, str):
            try:
                key_data = json.loads(key_data)
            except Exception:
                continue

        if not isinstance(key_data, dict) or "kty" not in key_data:
            continue

        signer = _build_signer_from_jwk(agent_id, key_data)
        if signer:
            return signer

    return None


def _build_signer_from_jwk(agent_id: str, key_data: dict) -> _NativeSigner | None:
    """Build a _NativeSigner from a JWK dict. Returns None on failure."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import base64

    if not isinstance(key_data, dict) or "kty" not in key_data:
        return None

    kty = key_data.get("kty")
    kid = key_data.get("kid", "")

    try:
        if kty == "OKP" and key_data.get("crv") == "Ed25519":
            d_bytes = base64.urlsafe_b64decode(key_data["d"] + "==")
            private_key = Ed25519PrivateKey.from_private_bytes(d_bytes)
            algorithm = "EdDSA"

        elif kty == "EC":
            from cryptography.hazmat.primitives.asymmetric.ec import (
                SECP256R1, SECP384R1, SECP521R1, derive_private_key,
            )
            crv = key_data.get("crv")
            crv_map = {"P-256": (SECP256R1(), "ES256"),
                       "P-384": (SECP384R1(), "ES384"),
                       "P-521": (SECP521R1(), "ES512")}
            if crv not in crv_map:
                return None
            curve, algorithm = crv_map[crv]
            d_bytes = base64.urlsafe_b64decode(key_data["d"] + "==")
            d_int = int.from_bytes(d_bytes, "big")
            private_key = derive_private_key(d_int, curve)

        else:
            return None

        if not kid:
            kid = _jwk_thumbprint(key_data)

        return _NativeSigner(agent_id, private_key, algorithm, kid, PROD_SERVER)

    except Exception:
        return None


def _jwk_thumbprint(jwk: dict) -> str:
    """Compute JWK thumbprint (SHA-256) per RFC 7638."""
    import hashlib
    import base64

    kty = jwk.get("kty")
    if kty == "OKP":
        members = {"crv": jwk["crv"], "kty": kty, "x": jwk["x"]}
    elif kty == "EC":
        members = {"crv": jwk["crv"], "kty": kty, "x": jwk["x"], "y": jwk["y"]}
    else:
        return ""

    # Lexicographic key order
    canonical = json.dumps(members, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ── CLI fallback ──────────────────────────────────────────────────────────────

def _resolve_binary() -> list[str]:
    """Find the auth-agent binary. Prefer global install over npx."""
    global _auth_binary
    if _auth_binary is not None:
        return _auth_binary

    path = shutil.which("auth-agent")
    if path:
        _auth_binary = [path]
        return _auth_binary

    _auth_binary = ["npx", "--yes", "@auth/agent-cli"]
    return _auth_binary


def _sign_jwt_cli(agent_id: str) -> str:
    """Sign JWT via CLI subprocess (~240ms)."""
    binary = _resolve_binary()
    cmd = [*binary, "sign", agent_id, "--capabilities", *ALL_CAPABILITIES]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

    if result.returncode != 0:
        raise RuntimeError(
            f"auth-agent sign failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}"
        )

    token = result.stdout.strip()
    if not token:
        raise RuntimeError("auth-agent sign returned empty token")

    lines = token.splitlines()
    if len(lines) > 1:
        token = max(lines, key=len)

    return token


# ── Public interface ──────────────────────────────────────────────────────────

def _load_agent_id() -> str | None:
    # 1. Environment variable (Render deployment)
    env_id = os.environ.get("AGENT_AUTH_AGENT_ID")
    if env_id:
        return env_id.strip()
    # 2. Local file (laptop)
    if os.path.exists(AGENT_ID_PATH):
        return open(AGENT_ID_PATH).read().strip() or None
    return None


def _save_agent_id(agent_id: str) -> None:
    os.makedirs(os.path.dirname(AGENT_ID_PATH), exist_ok=True)
    with open(AGENT_ID_PATH, "w") as f:
        f.write(agent_id)


def connect(server: str = PROD_SERVER) -> str:
    """
    Run the device-authorization flow. Prints a verification URL for
    human approval. Returns the agentId and saves it to disk.

    Only call this ONCE — subsequent runs reuse the saved agentId.
    """
    binary = _resolve_binary()
    cmd = [
        *binary,
        f"--url={server}",
        "connect",
        f"--provider={server}",
        "--capabilities", *ALL_CAPABILITIES,
    ]
    print(f"  Running: {' '.join(cmd)}")
    print("  A verification URL will appear — approve it in your browser.")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(
            f"auth-agent connect failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    output = result.stdout.strip()
    agent_id = _parse_agent_id(output)
    if not agent_id:
        raise RuntimeError(
            f"Could not parse agentId from auth-agent output:\n{output}"
        )

    _save_agent_id(agent_id)
    print(f"  Agent approved. ID: {agent_id}")
    return agent_id


def _parse_agent_id(output: str) -> str | None:
    """Extract agentId from CLI output."""
    for line in output.splitlines():
        line = line.strip()
        for prefix in ("agentId:", "Agent ID:", "agent_id:", "id:"):
            if line.lower().startswith(prefix.lower()):
                return line[len(prefix):].strip()
        if len(line) > 8 and " " not in line and not line.startswith("{"):
            return line
    return None


def sign_jwt(agent_id: str | None = None) -> str:
    """
    Mint a fresh single-use JWT for one API request.

    Tries Python-native signing first (~1ms). Falls back to CLI (~240ms)
    if the key can't be loaded from ~/.agent-auth.
    """
    global _native_signer, _native_tried

    if agent_id is None:
        agent_id = _load_agent_id()
    if not agent_id:
        raise RuntimeError(
            "No agent ID found. Run connect() first to approve the agent."
        )

    # Try native signing (fast path)
    if not _native_tried:
        _native_tried = True
        _native_signer = _try_load_native_signer(agent_id)
        if _native_signer:
            print("  [auth] Using Python-native JWT signing (~1ms per token)")
        else:
            print("  [auth] Falling back to CLI signing (~240ms per token)")

    if _native_signer:
        return _native_signer.sign(ALL_CAPABILITIES)

    # Fallback to CLI
    return _sign_jwt_cli(agent_id)


def get_agent_id() -> str | None:
    """Load saved agent ID, or None if not yet connected."""
    return _load_agent_id()
