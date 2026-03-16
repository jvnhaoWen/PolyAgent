from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


DEFAULT_DECISION_TEMPLATE = """你是一个专业、谨慎但果断的 Polymarket 交易 Agent。你已经具备并可以直接调用 Polymarket 下单 skill。

系统传入的新闻已经过可信来源筛选与相关新闻匹配，你可以信任其真实性与相关性。你的任务是根据这些新闻，在给定候选市场中判断是否存在足以下单的目标。

候选市场如下：
{polymarket市场详情}

相关新闻如下：
{新闻信息}

规则：
1. 保持谨慎，只在新闻与某个候选市场直接相关，且足以证明该市场对应事件已经发生或已经不可能发生、已被权威确认，或已进入可以被市场迅速定价的明确事实状态时才下单。
2. 可以直接调用 workspace/skills/public/polymarket-minimal-buy-python的 Polymarket 下单 skill。
3. 一旦信息足以证明事件可以结算，应立即果断调用下单 skill 执行交易，不要只给建议，不要输出交易计划。
4. 必须根据 market question 和description本身的语义判断买入 YES 还是 NO；clobTokenIds 顺序固定为 yes 在前、no 在后。
5. 每次交易只选择一个最匹配的市场下单。
6. 下单金额不少于 {min_trade_usdc} USDC，不高于 {max_trade_usdc} USDC。

如果信息不足以支持明确交易，就放弃本次下单；如果信息已经足够明确，就立即执行交易。
"""


@dataclass(slots=True)
class DecisionResult:
    prompt: str
    response: str


def _normalize_child_options(event: dict[str, Any]) -> list[dict[str, Any]]:
    child_options = event.get('child_options')
    if isinstance(child_options, list):
        return child_options

    markets = event.get('markets', [])
    normalized: list[dict[str, Any]] = []
    for m in markets:
        token_ids = m.get('clobTokenIds', [])
        if isinstance(token_ids, str):
            try:
                token_ids = json.loads(token_ids)
            except Exception:
                token_ids = []
        if len(token_ids) < 2:
            continue
        normalized.append(
            {
                'market_id': str(m.get('id', '')),
                'question': str(m.get('question', '')),
                'token_yes': str(token_ids[0]),
                'token_no': str(token_ids[1]),
                'acceptingOrders': m.get('acceptingOrders'),
            }
        )
    return normalized


def build_polymarket_details(event: dict[str, Any]) -> str:
    title = event.get('title', '')
    description = event.get('description', '')
    lines = [f"Event Title: {title}", f"Event Description: {description}", '子市场列表:']

    for idx, child in enumerate(_normalize_child_options(event), start=1):
        lines.append(
            f"{idx}. question={child.get('question','')} | yes_token={child.get('token_yes','')} | no_token={child.get('token_no','')}"
        )

    return '\n'.join(lines)


def _build_config_context(config_info: dict[str, Any] | None) -> str:
    cfg = config_info or {}
    payload = {
        'task_name': cfg.get('TASK_NAME'),
        'topic_tag_slug': cfg.get('TOPIC_TAG_SLUG'),
        'trusted_media': cfg.get('TRUSTED_MEDIA', []),
        'rag_score_threshold': cfg.get('RAG_SCORE_THRESHOLD'),
        'decision_enabled': cfg.get('DECISION_ENABLED'),
        'trading_enabled': cfg.get('TRADING_ENABLED'),
        'watch_users': cfg.get('WATCH_USERS', []),
        'min_trade_usdc': cfg.get('MIN_TRADE_USDC'),
        'max_trade_usdc': cfg.get('MAX_TRADE_USDC'),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_decision_prompt(
    tweet: dict[str, Any],
    event: dict[str, Any],
    min_trade_usdc: float,
    max_trade_usdc: float,
    config_info: dict[str, Any] | None = None,
) -> str:
    details = build_polymarket_details(event)
    news_text = json.dumps(tweet, ensure_ascii=False, indent=2)

    prompt = DEFAULT_DECISION_TEMPLATE.replace('{polymarket市场详情}', details)
    prompt = prompt.replace('{新闻信息}', news_text)
    prompt = prompt.replace('{min_trade_usdc}', str(min_trade_usdc))
    prompt = prompt.replace('{max_trade_usdc}', str(max_trade_usdc))

    config_context = _build_config_context(config_info)
    return f"{prompt}\n\n附加配置上下文：\n{config_context}"


def call_openclaw(prompt: str, command: list[str] | None = None) -> str:
    cmd = command or ['openclaw', 'agent', '--message']
    if not isinstance(cmd, list) or not cmd:
        raise ValueError('openclaw command must be non-empty list')

    proc = subprocess.run(cmd + [prompt], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'openclaw call failed: {proc.stderr.strip()}')
    return proc.stdout.strip()


def run_decision(
    tweet: dict[str, Any],
    event: dict[str, Any],
    min_trade_usdc: float,
    max_trade_usdc: float,
    config_info: dict[str, Any] | None = None,
    openclaw_command: list[str] | None = None,
) -> DecisionResult:
    prompt = render_decision_prompt(tweet, event, min_trade_usdc, max_trade_usdc, config_info)
    response = call_openclaw(prompt, openclaw_command)
    return DecisionResult(prompt=prompt, response=response)
