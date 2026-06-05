#!/usr/bin/env python3
"""
Extract Render env vars from ~/.agent-auth after running `python -m engine.play --connect`.

Usage:
  python scripts/extract_render_env.py

Prints the two env vars you need to set on Render:
  AGENT_AUTH_AGENT_ID=<your-agent-id>
  AGENT_AUTH_PRIVATE_KEY=<jwk-json>
"""
import glob
import json
import os
import sys


AUTH_DIR = os.path.expanduser("~/.agent-auth/agents")
AGENT_ID_FILE = os.path.join("data", "agent_id.txt")


def find_agent_id():
    """Load agent ID from data/agent_id.txt or env var."""
    env_id = os.environ.get("AGENT_AUTH_AGENT_ID")
    if env_id and env_id.strip():
        return env_id.strip()
    if os.path.exists(AGENT_ID_FILE):
        with open(AGENT_ID_FILE) as f:
            val = f.read().strip()
            if val:
                return val
    return None


def find_private_key(agent_id=None):
    """Search ~/.agent-auth/agents/*.json for the private key JWK."""
    if not os.path.isdir(AUTH_DIR):
        return None, None

    for fpath in glob.glob(os.path.join(AUTH_DIR, "*.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
        except Exception:
            continue

        # Extract agent ID from the file
        file_agent_id = (
            data.get("agentId")
            or data.get("agent_id")
            or data.get("id")
        )

        # If we know our agent_id, skip non-matching files
        if agent_id and file_agent_id and file_agent_id != agent_id:
            continue

        # Find the private key (JWK)
        key_data = (
            data.get("privateKey")
            or data.get("private_key")
            or data.get("keyPair", {}).get("privateKey")
            or data.get("agentKeypair", {}).get("privateKey")
            or data.get("keys", {}).get("privateKey")
        )

        if not key_data and "kty" in data:
            key_data = data  # whole object is the JWK

        if isinstance(key_data, str):
            try:
                key_data = json.loads(key_data)
            except Exception:
                continue

        if isinstance(key_data, dict) and "kty" in key_data:
            resolved_id = file_agent_id or agent_id
            return resolved_id, key_data

    return None, None


def main():
    agent_id = find_agent_id()
    resolved_id, private_key = find_private_key(agent_id)

    if not resolved_id:
        print("ERROR: No agent ID found.", file=sys.stderr)
        print("  Run `python -m engine.play --connect` first.", file=sys.stderr)
        sys.exit(1)

    if not private_key:
        print("ERROR: No private key found in ~/.agent-auth/agents/", file=sys.stderr)
        print("  Run `python -m engine.play --connect` first.", file=sys.stderr)
        sys.exit(1)

    key_json = json.dumps(private_key, separators=(",", ":"))

    print()
    print("  Set these two env vars on Render:")
    print()
    print(f"  AGENT_AUTH_AGENT_ID={resolved_id}")
    print(f"  AGENT_AUTH_PRIVATE_KEY={key_json}")
    print()
    print(f"  Key type: {private_key.get('kty')} / {private_key.get('crv', 'N/A')}")
    print(f"  Key ID:   {private_key.get('kid', 'auto-computed')}")
    print()


if __name__ == "__main__":
    main()
