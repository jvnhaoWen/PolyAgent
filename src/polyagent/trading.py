from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import AssetType, BalanceAllowanceParams, MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL


@dataclass(slots=True)
class TradeAction:
    side: str
    token_id: str
    amount_usd: float


class SimplePolymarketTrader:
    def __init__(self, private_key: str):
        self.private_key = private_key
        self.host = os.getenv('POLYMARKET_CLOB_HOST', 'https://clob.polymarket.com')
        self.chain_id = int(os.getenv('POLYMARKET_CHAIN_ID', '137'))
        self.signature_type = int(os.getenv('POLYMARKET_SIGNATURE_TYPE', '0'))
        self.funder = os.getenv('POLYMARKET_FUNDER') or None

        kwargs: dict[str, Any] = {
            'host': self.host,
            'chain_id': self.chain_id,
            'key': private_key,
            'signature_type': self.signature_type,
        }
        if self.funder:
            kwargs['funder'] = self.funder
        self.client = ClobClient(**kwargs)
        self.creds = None

    def initialize(self) -> None:
        self.creds = self.client.create_or_derive_api_creds()
        kwargs: dict[str, Any] = {
            'host': self.host,
            'chain_id': self.chain_id,
            'key': self.private_key,
            'creds': self.creds,
            'signature_type': self.signature_type,
        }
        if self.funder:
            kwargs['funder'] = self.funder
        self.client = ClobClient(**kwargs)

    def _ensure_allowance(self, asset_type: AssetType, token_id: str | None = None):
        params = BalanceAllowanceParams(asset_type=asset_type, token_id=token_id, signature_type=self.signature_type)
        current = self.client.get_balance_allowance(params)
        allowances = (current or {}).get('allowances', {})
        if any(int(v) > 0 for v in allowances.values() if str(v).isdigit()):
            return
        self.client.update_balance_allowance(params)

    def market_buy(self, token_id: str, amount: float) -> dict[str, Any]:
        self._ensure_allowance(AssetType.COLLATERAL)
        order = self.client.create_market_order(MarketOrderArgs(token_id=token_id, side=BUY, amount=amount))
        return self.client.post_order(order, OrderType.FOK)

    def market_sell(self, token_id: str, amount: float) -> dict[str, Any]:
        self._ensure_allowance(AssetType.CONDITIONAL, token_id=token_id)
        order = self.client.create_market_order(MarketOrderArgs(token_id=token_id, side=SELL, amount=amount))
        return self.client.post_order(order, OrderType.FOK)


def parse_trade_action_from_openclaw(text: str, max_asset_usd: float) -> TradeAction | None:
    """Expect model to return a JSON object in response body."""
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            return None
        payload = json.loads(text[start:end + 1])
    except Exception:
        return None

    side = str(payload.get('side', '')).lower()
    token_id = str(payload.get('token_id', '')).strip()
    amount_usd = float(payload.get('amount_usd', 0) or 0)

    if side not in {'buy', 'sell'} or not token_id or amount_usd <= 0:
        return None

    amount_usd = min(amount_usd, max_asset_usd)
    return TradeAction(side=side, token_id=token_id, amount_usd=amount_usd)
