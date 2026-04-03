import argparse
import base64
import json
from pathlib import Path
import sys
import time

import requests


def decode_jwt_payload(token: str):
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload + padding).decode("utf-8"))
    except Exception:
        return None


def short_claims(token: str):
    payload = decode_jwt_payload(token) or {}
    exp = payload.get("exp")
    return {
        "iss": payload.get("iss"),
        "aud": payload.get("aud"),
        "ou_code": payload.get("ou_code"),
        "scp": payload.get("scp"),
        "exp": exp,
        "exp_local": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp)) if isinstance(exp, int) else None,
    }


def derive_issuer_url(access_token: str, fallback_auth_host: str, fallback_auth_path: str):
    if access_token.startswith(("qts-", "eu-", "cn-")):
        return f"{fallback_auth_host.rstrip('/')}{fallback_auth_path}"
    payload = decode_jwt_payload(access_token) or {}
    issuer = payload.get("iss")
    if isinstance(issuer, str) and issuer.startswith("https://"):
        return issuer.rstrip("/")
    return f"{fallback_auth_host.rstrip('/')}{fallback_auth_path}"


def derive_api_base(access_token: str, configured_api_base: str):
    if configured_api_base:
        return configured_api_base.rstrip("/")
    issuer = derive_issuer_url(access_token, "https://auth.tesla.com", "/oauth2/v3")
    host = issuer.split("://", 1)[1].split("/", 1)[0] if "://" in issuer else issuer
    return "https://owner-api.vn.cloud.tesla.cn" if host.split(".")[-1] == "cn" else "https://owner-api.teslamotors.com"


def main():
    parser = argparse.ArgumentParser(description="Validate Tesla China Owner API tokens with TeslaMate-style refresh flow.")
    parser.add_argument("--access-token")
    parser.add_argument("--refresh-token")
    parser.add_argument("--from-config", default="")
    parser.add_argument("--auth-host", default="https://auth.tesla.com")
    parser.add_argument("--auth-path", default="/oauth2/v3")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--client-id", default="ownerapi")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    if args.from_config:
        config = json.loads(Path(args.from_config).read_text())
        if not args.access_token:
            args.access_token = config.get("tesla_access_token", "")
        if not args.refresh_token:
            args.refresh_token = config.get("tesla_refresh_token", "")

    if not args.access_token or not args.refresh_token:
        print("access token and refresh token are required")
        return 3

    print("== Access Token Claims ==")
    print(json.dumps(short_claims(args.access_token), ensure_ascii=False, indent=2))
    print("== Refresh Token Claims ==")
    print(json.dumps(short_claims(args.refresh_token), ensure_ascii=False, indent=2))

    issuer_url = derive_issuer_url(args.access_token, args.auth_host, args.auth_path)
    token_url = f"{issuer_url}/token"
    refresh_payload = {
        "grant_type": "refresh_token",
        "scope": "openid email offline_access",
        "client_id": args.client_id,
        "refresh_token": args.refresh_token,
    }
    print(f"\n== Refresh Request ==\nPOST {token_url}")
    resp = requests.post(token_url, json=refresh_payload, timeout=args.timeout)
    print(f"status={resp.status_code}")
    print(resp.text)

    if resp.status_code != 200:
        return 1

    body = resp.json()
    access_token = body.get("access_token", args.access_token)
    api_base = derive_api_base(args.access_token, args.api_base)
    api_url = f"{api_base}/api/1/users/me"
    print(f"\n== Profile Request ==\nGET {api_url}")
    profile_resp = requests.get(
        api_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=args.timeout,
    )
    print(f"status={profile_resp.status_code}")
    print(profile_resp.text)
    return 0 if profile_resp.status_code == 200 else 2


if __name__ == "__main__":
    sys.exit(main())
