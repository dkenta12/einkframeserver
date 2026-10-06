"""
Twilio SMS webhook receiver.

Run locally, expose with a Cloudflare Tunnel, then point your Twilio phone
number's "Inbound webhook" to: https://YOUR-TUNNEL-URL/sms
"""

import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, abort, request, send_file
from twilio.request_validator import RequestValidator

load_dotenv()

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")

_validator = RequestValidator(TWILIO_AUTH_TOKEN)


def require_twilio_signature(f):
    # Cloudflare always terminates TLS, so the public URL Twilio signed is
    # https even though Flask sees plain http from cloudflared internally.
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not TWILIO_AUTH_TOKEN:
            # Without a token the validator signs with an empty key, which anyone
            # can reproduce. Refuse rather than silently accept anything --
            # this endpoint is internet-facing.
            abort(403)
        url = request.url.rstrip("?").replace("http://", "https://", 1)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not _validator.validate(url, request.form.to_dict(), signature):
            abort(403)
        return f(*args, **kwargs)

    return wrapper


IMAGES_DIR = Path(__file__).parent / "received_images"
IMAGES_DIR.mkdir(exist_ok=True)

# Whatever the frame should currently display — overwritten on every new MMS.
LATEST_IMAGE = IMAGES_DIR / "latest.jpg"


@app.route("/sms", methods=["POST"])
@require_twilio_signature
def sms_webhook():
    body = request.form.get("Body", "")
    from_number = request.form.get("From", "unknown")
    to_number = request.form.get("To", "unknown")
    num_media = int(request.form.get("NumMedia", 0))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    divider = "=" * 50
    print(f"\n{divider}")
    print(f"[{timestamp}] New message received")
    print(f"From:     {from_number}")
    print(f"To:       {to_number}")
    print(f"Message:  {body}")
    print(f"NumMedia: {num_media}")

    for i in range(num_media):
        media_url = request.form.get(f"MediaUrl{i}")
        content_type = request.form.get(f"MediaContentType{i}", "")
        saved_path = _save_media(media_url, content_type, i)
        print(f"Media {i}: {content_type} -> {saved_path}")

    print(f"{divider}\n", flush=True)

    # Empty TwiML — no auto-reply for now
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        200,
        {"Content-Type": "text/xml"},
    )


def _is_twilio_media_url(url):
    # Media is fetched with the account SID and auth token as HTTP basic auth, so a
    # MediaUrl pointing anywhere else would hand those credentials to whoever asked.
    parts = urlparse(url)
    if parts.scheme != "https":
        return False
    host = (parts.hostname or "").lower()
    return host == "twilio.com" or host.endswith(".twilio.com")


def _save_media(media_url, content_type, index):
    if not media_url:
        return None
    if not _is_twilio_media_url(media_url):
        print(f"Refusing to fetch non-Twilio media URL: {media_url}", flush=True)
        return None
    ext = content_type.split("/")[-1] if "/" in content_type else "bin"
    filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{index}.{ext}"
    dest = IMAGES_DIR / filename

    # Twilio media URLs require HTTP Basic Auth with your Account SID + Auth Token
    resp = requests.get(
        media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=30
    )
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    LATEST_IMAGE.write_bytes(resp.content)
    return dest


@app.route("/latest", methods=["GET"])
def latest():
    if not LATEST_IMAGE.exists():
        return {"error": "no image received yet"}, 404
    return send_file(LATEST_IMAGE, mimetype="image/jpeg")


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"SMS/MMS receiver running on http://0.0.0.0:{port}")
    print(f"Webhook path: /sms")
    print(f"Saving media to: {IMAGES_DIR}")
    app.run(host="0.0.0.0", port=port, debug=True)
