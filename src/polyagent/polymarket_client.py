from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PolymarketClient:
    def __init__(
        self,
        gamma_base_url: str,
        clob_base_url: str,
        private_key: str | None = None,
        chain_id: int = 137,
        funder: str | None = None,
        signature_type: int = 1,
    ) -> None:
        self.gamma_base_url = gamma_base_url.rstrip("/")
        self.clob_base_url = clob_base_url.rstrip("/")
        self.private_key = private_key
        self.chain_id = chain_id
        self.funder = funder
        self.signature_type = signature_type
        self._clob_client: Any | None = None

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if v is not None}

    def build_gamma_url(self, endpoint: str, params: dict[str, Any]) -> str:
        clean = self._sanitize_params(params)
        query = urlencode(clean)
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        return f"{self.gamma_base_url}{endpoint}?{query}" if query else f"{self.gamma_base_url}{endpoint}"

    async def fetch_gamma(self, endpoint: str, params: dict[str, Any]) -> Any:
        url = self.build_gamma_url(endpoint, params)
        request = Request(url, headers={"User-Agent": "PolyAgent/1.0"})

        def _fetch() -> Any:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))

        return await asyncio.to_thread(_fetch)

    def _ensure_clob_client(self) -> Any:
        if self._clob_client is not None:
            return self._clob_client
        if not self.private_key:
            raise RuntimeError("POLYMARKET_PRIVATE_KEY is required for real CLOB trading")

        try:
            from py_clob_client.client import ClobClient
        except ImportError as exc:
            raise RuntimeError("py-clob-client package is required for real CLOB trading") from exc

        self._clob_client = ClobClient(
            host=self.clob_base_url,
            key=self.private_key,
            chain_id=self.chain_id,
            funder=self.funder,
            signature_type=self.signature_type,
        )
        return self._clob_client

    async def submit_order(self, order_payload: dict[str, Any]) -> dict[str, Any]:
        """Execute real CLOB orders with fallback simulation on unsupported payloads."""
        action = str(order_payload.get("action", "buy")).lower()
        if action not in {"buy", "sell"}:
            return {
                "status": "simulated",
                "payload": order_payload,
                "hint": "split/merge/redeem require separate on-chain position operations.",
            }

        token_id = order_payload.get("token_id")
        price = float(order_payload.get("price", 0))
        size = float(order_payload.get("size", 0))
        if not token_id or price <= 0 or size <= 0:
            raise ValueError("order payload requires token_id, positive price and size")

        client = self._ensure_clob_client()

        def _submit() -> dict[str, Any]:
            side = "BUY" if action == "buy" else "SELL"
            order_args = {
                "token_id": token_id,
                "price": price,
                "size": size,
                "side": side,
            }
            # py-clob-client API shape can vary; this path matches current official examples.
            signed_order = client.create_order(order_args)
            response = client.post_order(signed_order, order_type="GTC")
            return {"status": "submitted", "response": response, "payload": order_payload}

        try:
            return await asyncio.to_thread(_submit)
        except Exception as exc:
            logging.exception("Real CLOB order failed; returning explicit failure")
            return {
                "status": "failed",
                "error": str(exc),
                "payload": order_payload,
            }
