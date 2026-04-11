"""
adapters/verimedia_adapter.py

VeriMedia Live Attack Adapter
Target: https://github.com/FlashCarrot/VeriMedia
Server: Flask app on http://127.0.0.1:5004

VeriMedia accepts file uploads (text/audio/video) and returns HTML results.
This adapter wraps the /upload endpoint, sending adversarial text as .txt files
and parsing the HTML response for toxicity level and analysis content.
"""

import http.client
import os
import re
import tempfile
import requests
from .base_adapter import TargetAgentAdapter, AdapterTimeoutError, AdapterUnavailableError

# Flask stores analysis results in session cookies; for long reports these
# can exceed Python http.client's default 65536-byte line limit. Raise it once.
http.client._MAXLINE = 655360
http.client._MAXHEADERS = 500


class VeriMediaAdapter(TargetAgentAdapter):
    """
    Adapter for VeriMedia's file-upload text analysis endpoint.

    Attack surface:
    - POST /upload  multipart/form-data  file_type=text  file=<.txt>
    - Response: HTML page with toxicity level (None/Mild/High/Max)
    - Fine-tuned toxicity classifier (ft:gpt-3.5-turbo-0125)
    - No authentication, no rate limiting, 500MB upload limit
    """

    def __init__(self, base_url: str = "http://127.0.0.1:5004", timeout_seconds: int = 60):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = requests.Session()

    # Flask session cookies max ~4KB before hitting HTTP limits. Keep file content under
    # this threshold to prevent LineTooLong response errors from the server.
    _MAX_FILE_BYTES = 3000

    def send_message(self, message: str) -> str:
        """
        Send adversarial text to VeriMedia's /upload endpoint.
        Writes message to a temp .txt file, POSTs as multipart form.
        Returns the toxicity level + key analysis text extracted from HTML.
        """
        # Truncate to avoid Flask session cookie overflow (LineTooLong errors)
        content = message[:self._MAX_FILE_BYTES]

        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                tmp = f.name

            # Use a fresh session per request — avoids cookie accumulation from
            # previous large responses which causes LineTooLong on subsequent calls.
            one_shot = requests.Session()
            with open(tmp, "rb") as fh:
                resp = one_shot.post(
                    f"{self._base_url}/upload",
                    data={"file_type": "text"},
                    files={"file": ("attack_input.txt", fh, "text/plain")},
                    timeout=self._timeout,
                    allow_redirects=True,
                )

            if resp.status_code == 302 or (resp.status_code == 200 and "No file" in resp.text):
                return "ERROR: upload rejected (redirect/no file)"

            if resp.status_code != 200:
                raise AdapterUnavailableError(f"HTTP {resp.status_code}")

            return self._parse_response(resp.text)

        except requests.Timeout:
            raise AdapterTimeoutError(f"VeriMedia /upload timed out after {self._timeout}s")
        except requests.ConnectionError as e:
            raise AdapterUnavailableError(f"VeriMedia unreachable: {e}")
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    def _parse_response(self, html: str) -> str:
        """Extract toxicity level + suggestions from VeriMedia results HTML."""
        parts = []

        # Primary: hidden input value used for PDF export (most reliable)
        m = re.search(r'name="toxicity_level"\s+value="([^"]+)"', html)
        if not m:
            # Fallback: badge/span near "Toxicity Level" heading
            m = re.search(
                r'Toxicity Level[\s\S]{0,200}?<(?:span|div|strong)[^>]*>\s*(None|Mild|High|Max)\s*</',
                html, re.IGNORECASE
            )
        if not m:
            m = re.search(r'\b(None|Mild|High|Max)\b', html)

        level = m.group(1) if m else "unknown"
        parts.append(f"TOXICITY_LEVEL: {level}")

        # Improvement suggestions (li items inside suggestion containers)
        sugs = re.findall(
            r'class="[^"]*suggestion[^"]*"[^>]*>(.*?)</(?:li|div)>',
            html, re.DOTALL | re.IGNORECASE
        )
        if not sugs:
            sugs = re.findall(r'<li[^>]*>\s*([A-Z][^<]{20,300})\s*</li>', html)
        cleaned = [re.sub(r'<[^>]+>', '', s).strip() for s in sugs if len(s.strip()) > 20]
        if cleaned:
            parts.append("SUGGESTIONS: " + " | ".join(cleaned[:3]))

        # Report content hidden field
        m2 = re.search(r'name="report_content"\s+value="([^"]{20,})"', html)
        if m2:
            parts.append("REPORT: " + m2.group(1)[:400])

        return "\n".join(parts)

    def reset_session(self) -> None:
        self._session = requests.Session()

    def get_agent_info(self) -> dict:
        return {
            "name": "VeriMedia",
            "type": "flask_file_upload",
            "base_url": self._base_url,
            "endpoint": "/upload",
            "input_format": "multipart/form-data (file_type=text, file=*.txt)",
            "model": "ft:gpt-3.5-turbo-0125:personal:toxicity-classifier",
            "auth": "none",
        }

    def is_available(self) -> bool:
        """
        Smoke-test the live target by uploading a benign text file and checking
        that VeriMedia returns a valid toxicity level (None/Mild/High/Max).
        If the target has no OpenAI key or is misconfigured, the response will
        be unparseable and this returns False → caller falls back to doc mode.
        """
        import tempfile, os as _os
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write("Hello, this is a test message.")
                tmp = f.name

            with open(tmp, "rb") as fh:
                resp = requests.Session().post(
                    f"{self._base_url}/upload",
                    data={"file_type": "text"},
                    files={"file": ("smoke_test.txt", fh, "text/plain")},
                    timeout=15,
                    allow_redirects=True,
                )

            if resp.status_code != 200:
                return False

            # Valid only if VeriMedia's classifier returned a recognised level
            parsed = self._parse_response(resp.text)
            return any(
                f"TOXICITY_LEVEL: {lvl}" in parsed
                for lvl in ("None", "Mild", "High", "Max")
            )
        except Exception:
            return False
        finally:
            if tmp and _os.path.exists(tmp):
                _os.unlink(tmp)
