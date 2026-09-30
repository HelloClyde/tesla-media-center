"""Check whether a Douyin visitor session can be established without Chrome.

This is a diagnostic tool, not the app's login or video resolver. It executes
only the inline scripts from Douyin's initial challenge in a resource-limited
QuickJS context. Cookie values stay in memory and are never printed.
"""

import argparse
import json
import re
from urllib.parse import quote, urlencode

import quickjs
from curl_cffi import requests
from .signing.abogus import ABogus


HOME = "https://www.douyin.com/"
PASSPORT = "https://login.douyin.com/passport/web/"
SCRIPT = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script\s*>", re.I | re.S)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def challenge_cookies(html: str, nonce: str) -> dict[str, str]:
    """Run the site's nonce script in an isolated JS runtime."""
    scripts = SCRIPT.findall(html)
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", nonce) or not 1 <= len(scripts) <= 4:
        raise ValueError("Unexpected initial challenge")
    if "byted_acrawler.init" not in html or sum(map(len, scripts)) > 150_000:
        raise ValueError("Unrecognized challenge script")

    context = quickjs.Context()
    context.set_memory_limit(32 * 1024 * 1024)
    context.set_max_stack_size(1024 * 1024)
    context.set_time_limit(5)
    nonce_cookie = json.dumps("__ac_nonce=" + nonce)
    context.eval(
        "var window=globalThis, global=globalThis, saved={};"
        "var document={referrer:''};"
        "Object.defineProperty(document,'cookie',{"
        "get:function(){return " + nonce_cookie + "},"
        "set:function(value){var part=value.split(';',1)[0];"
        "var i=part.indexOf('=');if(i>0)saved[part.slice(0,i)]=part.slice(i+1)}});"
        "var navigator={userAgent:" + json.dumps(USER_AGENT) + ","
        "language:'zh-CN',languages:['zh-CN','zh'],platform:'Win32',"
        "hardwareConcurrency:8,deviceMemory:8,webdriver:false,plugins:[]};"
        "var location={href:" + json.dumps(HOME) + ",origin:'https://www.douyin.com',"
        "hostname:'www.douyin.com',protocol:'https:',reload:function(){}};"
        "window.location=location;"
        "var screen={width:1920,height:1080,availWidth:1920,availHeight:1040,colorDepth:24};"
        "var performance={now:function(){return 1000},"
        "timing:{navigationStart:Date.now()-1000}};"
        "var sessionStorage={setItem:function(){},getItem:function(){return null}};"
        "var localStorage={setItem:function(){},getItem:function(){return null}};"
        "var setTimeout=function(){return 0},clearTimeout=function(){};"
    )
    for script in scripts:
        context.eval(script)
    cookies = json.loads(context.eval("JSON.stringify(saved)"))
    signature = cookies.get("__ac_signature", "")
    if not isinstance(signature, str) or not 20 <= len(signature) <= 200:
        raise ValueError("Challenge did not produce a signature")
    return {name: value for name, value in cookies.items()
            if name in ("__ac_signature", "__ac_referer") and isinstance(value, str)}


def create_visitor_session():
    session = requests.Session(impersonate="chrome", headers={"User-Agent": USER_AGENT})
    response = session.get(HOME, timeout=20)
    if response.status_code != 200 or response.url != HOME:
        raise ValueError("Initial page request was rejected")
    nonce = session.cookies.get("__ac_nonce")
    for name, value in challenge_cookies(response.text, nonce).items():
        session.cookies.set(name, value, domain=".douyin.com", path="/")
    response = session.get(HOME, timeout=20)
    if response.status_code != 200 or "byted_acrawler.init" in response.text:
        raise ValueError("Challenge retry was rejected")
    if not session.cookies.get("UIFID_TEMP") or not session.cookies.get("ttwid"):
        raise ValueError("Server did not issue a visitor identity")
    return session


def get_qrcode(session):
    response = session.get(
        PASSPORT + "get_qrcode/",
        params={"aid": "6383", "is_from_ttaccountsdk": "1", "next": "https://www.douyin.com"},
        headers={"Referer": HOME, "Origin": "https://www.douyin.com"},
        timeout=20,
    )
    data = response.json().get("data", {})
    if response.status_code != 200 or data.get("error_code") != 0:
        raise ValueError(f"QR creation rejected (code={data.get('error_code')})")
    if not data.get("token") or not data.get("qrcode"):
        raise ValueError("QR response was incomplete")
    return data


def check_qrcode(session, token: str, is_frontier: bool = True):
    if not token or len(token) > 200:
        raise ValueError("Invalid QR token")
    query = urlencode({
        "passport_jssdk_version": "3.4.9",
        "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": "1",
        "aid": "6383",
        "language": "zh",
        "account_app_language": "zh-CN",
    })
    body = urlencode({
        "need_logo": "false", "is_frontier": str(is_frontier).lower(),
        "token": token, "is_new_login": "1", "next": "https://www.douyin.com",
        "need_short_url": "true",
    })
    bogus = ABogus(USER_AGENT).get_value(query, body=body)
    response = session.post(
        PASSPORT + "check_qrconnect/?" + query + "&a_bogus=" + quote(bogus, safe=""),
        data=body,
        headers={"Referer": HOME, "Origin": "https://www.douyin.com",
                 "Content-Type": "application/x-www-form-urlencoded"},
        timeout=20,
    )
    data = response.json().get("data", {})
    if response.status_code != 200 or data.get("error_code") != 0:
        raise ValueError(f"QR polling rejected (code={data.get('error_code')})")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--check-qr", action="store_true",
                        help="also create a QR code and poll once; does not display its value")
    args = parser.parse_args()
    if not 1 <= args.attempts <= 10:
        parser.error("--attempts must be between 1 and 10")
    failures = 0
    for index in range(args.attempts):
        try:
            session = create_visitor_session()
            print(f"attempt {index + 1}: visitor identity issued "
                  f"(UIFID_TEMP={bool(session.cookies.get('UIFID_TEMP'))}, "
                  f"ttwid={bool(session.cookies.get('ttwid'))})")
            if args.check_qr:
                qr = get_qrcode(session)
                state = check_qrcode(session, qr["token"], qr.get("is_frontier", False))
                print(f"attempt {index + 1}: QR issued and polled (status={state.get('status')})")
            session.close()
        except Exception as error:
            failures += 1
            print(f"attempt {index + 1}: failed ({type(error).__name__}: {error})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
