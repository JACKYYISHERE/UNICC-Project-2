"""
petri_agent_adapter.py  —  Expert 1 adapter for Petri UNICC Compliance Judge

Connects Expert 1's live attack engine to the petri_server.py Flask endpoint.
Uses duck-typing (no direct inheritance from TargetAgentAdapter) to avoid the
Expert1/types.py circular import issue.

Target Agent Profile
--------------------
Name:    Petri — UNICC AI Safety Compliance Advisor
Purpose: Evaluates AI systems for compliance with international governance
         standards (EU AI Act, US AI BoR, IEEE 7001/7003/7009, UNESCO)
API:     Dify-compatible  POST /v1/workflows/run
Auth:    None (internal UN deployment simulation)

Attack Surface
--------------
The Petri agent has three confirmed vulnerability classes:

  VULN-1  AML.T0051 — LLM Prompt Injection via Indirect Reference
          The judge embeds user content into <transcript>…</transcript>
          XML. Injecting </transcript></evaluation><evaluation> can
          short-circuit score parsing.

  VULN-2  AML.T0054 — LLM Jailbreak (Authority Framing)
          Citing "UNICC/EU AI Act pre-approval" tokens tricks the judge
          into assigning LOW risk tiers without genuine review.

  VULN-3  AML.CS0039 — Prompt Injection via Embedded Score Block
          Embedding a full "example compliant evaluation" block biases
          the judge's in-context few-shot examples, causing it to copy
          injected scores.
"""

from __future__ import annotations

import uuid
import requests


class PetriAgentAdapter:
    """
    Adapter for the Petri UNICC AI Compliance Judge.

    Implements the same duck-typed interface as XenophobiaToolAdapter
    so Expert 1 can drop this in without any other code changes.
    """

    def __init__(
        self,
        base_url:        str = "http://localhost:5002",
        timeout_seconds: int = 45,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout  = timeout_seconds
        self._session_id = str(uuid.uuid4())

    # ── TargetAgentAdapter duck-typed interface ───────────────────────────────

    def send_message(self, message: str) -> str:
        """
        POST message to Petri and return its compliance evaluation text.

        Catches all network / HTTP errors and returns them as a plain-text
        error string so expert1_router's probe / boundary / attack loops can
        record the failure without crashing.
        """
        url = f"{self._base_url}/v1/workflows/run"
        payload = {
            "inputs":        {"query": message},
            "user":          self._session_id,
            "response_mode": "blocking",
        }
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            outputs = data.get("data", {}).get("outputs", {})
            result  = outputs.get("result") or outputs.get("text") or str(data)
            return result
        except requests.exceptions.Timeout:
            return f"[ADAPTER_ERROR: Petri server timed out after {self._timeout}s]"
        except requests.exceptions.ConnectionError as e:
            return f"[ADAPTER_ERROR: Cannot reach Petri server at {self._base_url}: {e}]"
        except requests.exceptions.HTTPError as e:
            return f"[ADAPTER_ERROR: HTTP {e.response.status_code} — {e}]"
        except Exception as e:
            return f"[ADAPTER_ERROR: {type(e).__name__}: {e}]"

    def reset_session(self) -> None:
        """Generate a new session ID and optionally clear server-side history."""
        old_id = self._session_id
        self._session_id = str(uuid.uuid4())
        try:
            requests.delete(
                f"{self._base_url}/sessions/{old_id}",
                timeout=5,
            )
        except Exception:
            pass  # best-effort; server may not support DELETE

    def get_agent_info(self) -> dict:
        return {
            "name":        "Petri — UNICC AI Safety Compliance Advisor",
            "type":        "compliance_judge",
            "base_url":    self._base_url,
            "description": (
                "Evaluates AI system interactions for compliance with EU AI Act, "
                "US AI BoR, IEEE 7001/7003/7009, UNESCO AI Ethics. "
                "Attack surface: XML injection, authority-framing bypass, "
                "dimension-score forgery."
            ),
            "vulnerabilities": [
                "AML.T0051 — XML tag injection into <transcript> slot",
                "AML.T0054 — Authority framing / fake pre-approval bypass",
                "AML.CS0039 — In-context score forgery via embedded examples",
            ],
        }

    def is_available(self) -> bool:
        """Return True iff the petri_server health endpoint is reachable."""
        try:
            resp = requests.get(f"{self._base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
