from __future__ import annotations

import asyncio
import json
import webbrowser
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx2
from pydantic import AnyUrl

from mcp import ClientSession
from mcp.client.auth import (
    AuthorizationCodeResult,
    OAuthClientProvider,
    TokenStorage,
)
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_FILE = Path.home() / ".robinhood_mcp_tokens.json"

AGENTIC_NICKNAME = "Agentic"

# SAFETY GATE:
# This client is intentionally read-only.
LIVE_ORDER_EXECUTION = False


LEVERAGE_MULTIPLIERS = {
    "UPRO": Decimal("3"),
    "DFEN": Decimal("3"),
}


READ_ONLY_TOOLS = {
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_quotes",
    "get_equity_tax_lots",
}


class FileTokenStorage(TokenStorage):
    """Persist Robinhood MCP OAuth tokens locally."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientInformationFull | None = None

        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            data = json.loads(
                self.path.read_text(encoding="utf-8")
            )

            if not isinstance(data, dict):
                return

            tokens = data.get("tokens")
            if tokens:
                self._tokens = OAuthToken(**tokens)

            client_info = data.get("client_info")
            if client_info:
                self._client_info = OAuthClientInformationFull(
                    **client_info
                )

        except Exception:
            # A corrupt token file should not prevent a fresh OAuth flow.
            self._tokens = None
            self._client_info = None

    def _save(self) -> None:
        data = {
            "tokens": (
                self._tokens.model_dump(mode="json")
                if self._tokens
                else None
            ),
            "client_info": (
                self._client_info.model_dump(mode="json")
                if self._client_info
                else None
            ),
        }

        self.path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        self._save()

    async def get_client_info(
        self,
    ) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        self._client_info = client_info
        self._save()


CALLBACK_RESULT: dict | None = None
CALLBACK_SERVER = None


async def _handle_callback_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Receive the OAuth redirect on localhost."""

    global CALLBACK_RESULT, CALLBACK_SERVER

    try:
        request = await reader.read(65535)
        request_text = request.decode(
            "utf-8",
            errors="replace",
        )

        lines = request_text.splitlines()

        if not lines:
            writer.write(
                b"HTTP/1.1 400 Bad Request\r\n\r\n"
            )
            await writer.drain()
            return

        parts = lines[0].split()

        if len(parts) < 2:
            writer.write(
                b"HTTP/1.1 400 Bad Request\r\n\r\n"
            )
            await writer.drain()
            return

        method, path = parts[0], parts[1]

        if method != "GET":
            writer.write(
                b"HTTP/1.1 405 Method Not Allowed\r\n\r\n"
            )
            await writer.drain()
            return

        parsed = urlparse(path)
        query = parse_qs(parsed.query)

        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]

        if code:
            CALLBACK_RESULT = {
                "code": code,
                "state": state,
            }

            body = (
                "<html><body>"
                "<h1>Authorization complete</h1>"
                "<p>You can close this window and return to ClaudeTrade.</p>"
                "</body></html>"
            ).encode()

            headers = (
                b"HTTP/1.1 200 OK\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Content-Type: text/html; charset=utf-8\r\n"
                + b"Connection: close\r\n"
                + b"\r\n"
            )

            writer.write(headers)
            writer.write(body)
            await writer.drain()

        else:
            CALLBACK_RESULT = None

            body = (
                "<html><body>"
                "<h1>Authorization failed</h1>"
                "<p>No authorization code was returned.</p>"
                "</body></html>"
            ).encode()

            headers = (
                b"HTTP/1.1 400 Bad Request\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Content-Type: text/html; charset=utf-8\r\n"
                + b"Connection: close\r\n"
                + b"\r\n"
            )

            writer.write(headers)
            writer.write(body)
            await writer.drain()

    finally:
        writer.close()

        try:
            await writer.wait_closed()
        except Exception:
            pass

        CALLBACK_SERVER = None


async def start_callback_server():
    global CALLBACK_SERVER

    if CALLBACK_SERVER is not None:
        return CALLBACK_SERVER

    CALLBACK_SERVER = await asyncio.start_server(
        _handle_callback_request,
        "127.0.0.1",
        8765,
    )

    return CALLBACK_SERVER


def _oauth_url() -> str:
    return (
        f"{ROBINHOOD_MCP_URL}"
        "/authorize"
        "?redirect_uri=http://localhost:8765/callback"
    )


async def redirect_handler(url: str | AnyUrl) -> None:
    """Open the OAuth authorization URL."""

    url_string = str(url)

    print()
    print(
        "Open the browser window for Robinhood authentication."
    )
    print(url_string)
    print()

    webbrowser.open(url_string)


async def callback_handler() -> AuthorizationCodeResult:
    """Wait for the localhost OAuth callback."""

    global CALLBACK_RESULT

    await start_callback_server()

    deadline = (
        asyncio.get_running_loop().time() + 180
    )

    while CALLBACK_RESULT is None:
        if (
            asyncio.get_running_loop().time()
            >= deadline
        ):
            raise TimeoutError(
                "Timed out waiting for Robinhood OAuth callback."
            )

        await asyncio.sleep(0.25)

    result = CALLBACK_RESULT
    CALLBACK_RESULT = None

    return AuthorizationCodeResult(
        code=result["code"],
        state=result.get("state"),
    )


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def extract_data(result) -> dict:
    """Extract structured MCP result data."""

    content = getattr(
        result,
        "structured_content",
        None,
    )

    if content is None:
        content = getattr(
            result,
            "structuredContent",
            None,
        )

    if not isinstance(content, dict):
        raise RuntimeError(
            f"Unexpected MCP response shape: {content!r}"
        )

    # Some MCP tools return {"data": {...}}.
    data = content.get("data")

    if isinstance(data, dict):
        return data

    return content


async def call_read_only(
    session,
    name: str,
    arguments: dict | None = None,
):
    """Call only explicitly approved read-only tools."""

    if name not in READ_ONLY_TOOLS:
        raise RuntimeError(
            f"BLOCKED: {name} is not in the read-only allowlist."
        )

    if LIVE_ORDER_EXECUTION:
        raise RuntimeError(
            "LIVE_ORDER_EXECUTION must remain False "
            "for the read-only Robinhood client."
        )

    return await session.call_tool(
        name,
        arguments=arguments or {},
    )


async def select_agentic_account(session) -> str:
    """Find the Robinhood account explicitly enabled for agentic access."""

    result = await call_read_only(
        session,
        "get_accounts",
    )

    data = extract_data(result)

    accounts = (
        data.get("accounts")
        or data.get("data")
        or []
    )

    if isinstance(accounts, dict):
        accounts = [accounts]

    if not isinstance(accounts, list):
        raise RuntimeError(
            f"Unexpected accounts payload: {accounts!r}"
        )

    eligible = [
        account
        for account in accounts
        if isinstance(account, dict)
        and account.get("agentic_allowed") is True
    ]

    if not eligible:
        raise RuntimeError(
            "No Robinhood account with agentic_allowed=true was found."
        )

    if len(eligible) > 1:
        raise RuntimeError(
            f"Expected one Agentic account, found {len(eligible)}."
        )

    account = eligible[0]

    account_number = (
        account.get("account_number")
        or account.get("accountNumber")
    )

    if not account_number:
        raise RuntimeError(
            "Selected Agentic account is missing an account_number."
        )

    return str(account_number)


def extract_symbols(
    positions: dict,
) -> list[str]:
    """Extract unique symbols from the live position payload."""

    rows = positions.get("positions", [])

    if not isinstance(rows, list):
        return []

    symbols: list[str] = []
    seen: set[str] = set()

    for position in rows:
        if not isinstance(position, dict):
            continue

        symbol = str(
            position.get("symbol", "")
        ).upper().strip()

        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)

    return symbols

def normalize_portfolio(
    portfolio: dict,
    positions: dict,
    quotes: dict,
) -> dict:
    """Convert Robinhood MCP payloads into ClaudeTrade's normalized model."""

    # Robinhood uses `total_value` for the portfolio's current value.
    portfolio_value = Decimal(
        str(portfolio.get("total_value", 0) or 0)
    )

    # Robinhood returns buying_power as a nested object:
    #
    # "buying_power": {
    #     "buying_power": "0.0000",
    #     "unleveraged_buying_power": "0.0000",
    #     "display_currency": "USD"
    # }
    raw_buying_power = portfolio.get("buying_power", 0)

    if isinstance(raw_buying_power, dict):
        raw_buying_power = raw_buying_power.get(
            "buying_power",
            0,
        )

    buying_power = Decimal(
        str(raw_buying_power or 0)
    )

    # Robinhood get_equity_quotes returns:
    #
    # {
    #     "results": [
    #         {
    #             "quote": {
    #                 "symbol": "TSLA",
    #                 "last_trade_price": "327.450000",
    #                 ...
    #             },
    #             "close": {...}
    #         }
    #     ]
    # }
    #
    # Normalize this into:
    #
    # {
    #     "TSLA": Decimal("327.45"),
    #     ...
    # }
    quote_map: dict[str, Decimal] = {}

    quote_results = (
        quotes.get("results", [])
        if isinstance(quotes, dict)
        else []
    )

    if isinstance(quote_results, dict):
        quote_results = [quote_results]

    for result in quote_results:
        if not isinstance(result, dict):
            continue

        quote = result.get("quote", {})

        if not isinstance(quote, dict):
            continue

        symbol = str(
            quote.get("symbol", "")
        ).upper()

        if not symbol:
            continue

        # Prefer the most recent trade price.
        # Fall back to non-regular-hours price and then
        # previous close if necessary.
        raw_price = (
            quote.get("last_trade_price")
            or quote.get("last_non_reg_trade_price")
            or quote.get("previous_close")
            or 0
        )

        quote_map[symbol] = Decimal(
            str(raw_price or 0)
        )

    normalized_positions: dict[str, dict] = {}

    position_rows = positions.get(
        "positions",
        [],
    )

    if isinstance(position_rows, dict):
        position_rows = [position_rows]

    for position in position_rows:
        if not isinstance(position, dict):
            continue

        symbol = str(
            position.get("symbol", "")
        ).upper()

        if not symbol:
            continue

        quantity = Decimal(
            str(
                position.get(
                    "quantity",
                    0,
                )
                or 0
            )
        )

        # Current market price comes from get_equity_quotes.
        last_price = quote_map.get(symbol)

        # Fallback in case Robinhood eventually provides a
        # price directly in the position payload.
        if last_price is None:
            raw_price = (
                position.get("last_price")
                or position.get("price")
                or 0
            )

            last_price = Decimal(
                str(raw_price or 0)
            )

        # Robinhood's position payload does not contain
        # market_value, so calculate it ourselves.
        market_value = quantity * last_price

        # Portfolio weight.
        weight = (
            market_value / portfolio_value
            if portfolio_value
            else Decimal("0")
        )

        # Leveraged ETF exposure.
        leverage = LEVERAGE_MULTIPLIERS.get(
            symbol,
            Decimal("1"),
        )

        effective_leverage_contribution = (
            weight * leverage
        )

        normalized_positions[symbol] = {
            "quantity": str(quantity),
            "last_price": str(last_price),
            "market_value": str(market_value),
            "weight": str(
                weight.quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP,
                )
            ),
            "leverage_multiplier": str(leverage),
            "effective_leverage_contribution": str(
                effective_leverage_contribution.quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP,
                )
            ),
        }

    return {
        "portfolio_value": str(
            portfolio_value.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        ),
        "buying_power": str(
            buying_power.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        ),
        "positions": normalized_positions,
    }

async def read_live_tax_lots(
    session,
    account_number: str,
    symbols: list[str],
) -> dict[str, list]:
    """Read tax lots for the specified live positions."""

    results: dict[str, list] = {}

    for symbol in symbols:
        result = await call_read_only(
            session,
            "get_equity_tax_lots",
            {
                "account_number": account_number,
                "symbol": symbol,
            },
        )

        data = extract_data(result)

        rows = (
            data.get("taxLots")
            or data.get("tax_lots")
            or data.get("positions")
            or []
        )

        if isinstance(rows, dict):
            rows = [rows]

        if not isinstance(rows, list):
            raise RuntimeError(
                f"Unexpected tax-lot payload for "
                f"{symbol}: {rows!r}"
            )

        results[symbol] = rows

    return results


def flatten_tax_lots(
    tax_lots_by_symbol: dict[str, list],
) -> dict:
    """Convert symbol-keyed lots into Portfolio model format."""

    lots = []

    for symbol, rows in tax_lots_by_symbol.items():
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            lot = dict(row)
            lot.setdefault("symbol", symbol)
            lots.append(lot)

    return {
        "lots": lots,
    }


async def read_live_portfolio(
    session,
    account_number: str,
) -> dict:
    """Read the complete live portfolio, dynamically from positions."""

    portfolio_result = await call_read_only(
        session,
        "get_portfolio",
        {
            "account_number": account_number,
        },
    )

    positions_result = await call_read_only(
        session,
        "get_equity_positions",
        {
            "account_number": account_number,
        },
    )

    portfolio = extract_data(
        portfolio_result
    )

    positions = extract_data(
        positions_result
    )

    symbols = extract_symbols(
        positions
    )


    # IMPORTANT:
    # Quotes are based on the actual positions,
    # not a hard-coded watchlist.
    quotes = {}

    if symbols:
        quotes_result = await call_read_only(
            session,
            "get_equity_quotes",
            {
                "symbols": symbols,
            },
        )

        quotes = extract_data(
            quotes_result
        )

    tax_lots_by_symbol = {}

    if symbols:
        tax_lots_by_symbol = await read_live_tax_lots(
            session,
            account_number,
            symbols,
        )

    tax_lots = flatten_tax_lots(
        tax_lots_by_symbol
    )

    normalized = normalize_portfolio(
        portfolio,
        positions,
        quotes,
    )

    # print("\nRAW QUOTES:")
    # print(json.dumps(quotes, indent=2, default=str))

    # print("\nRAW PORTFOLIO:")
    # print(json.dumps(portfolio, indent=2, default=str))

    # print("\nRAW POSITIONS:")
    # print(json.dumps(positions, indent=2, default=str))

    return {
        "portfolio": portfolio,
        "positions": positions,
        "quotes": quotes,
        "tax_lots": tax_lots,
        "normalized": normalized,
        "symbols": symbols,
    }


def print_portfolio_report(
    payload: dict,
) -> None:
    """Print a human-readable read-only portfolio report."""

    normalized = payload["normalized"]

    print()
    print(
        "ClaudeTrade — Robinhood Portfolio"
    )
    print("=" * 60)

    print(
        f"Portfolio value: "
        f"${normalized['portfolio_value']}"
    )

    print(
        f"Buying power:    "
        f"${normalized['buying_power']}"
    )

    print()
    print("Positions")
    print("-" * 60)

    positions = normalized["positions"]

    if not positions:
        print("No positions.")

    for symbol, position in positions.items():
        print(
            f"{symbol:8s} "
            f"weight={position['weight']:>8s} "
            f"value=${position['market_value']:>12s} "
            f"leverage={position['leverage_multiplier']}x"
        )

    print()
    print(
        f"Tax lots: {len(payload['tax_lots']['lots'])}"
    )

    print()
    print(
        "LIVE ORDER EXECUTION: "
        f"{'ENABLED' if LIVE_ORDER_EXECUTION else 'DISABLED'}"
    )


async def main():
    if LIVE_ORDER_EXECUTION:
        raise RuntimeError(
            "Refusing to start: "
            "LIVE_ORDER_EXECUTION must be False."
        )

    storage = FileTokenStorage(
        TOKEN_FILE
    )

    oauth_provider = OAuthClientProvider(
        server_url=ROBINHOOD_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="ClaudeTrade Robinhood MCP Client",
            redirect_uris=[
                AnyUrl(
                    "http://localhost:8765/callback"
                )
            ],
            grant_types=[
                "authorization_code",
                "refresh_token",
            ],
            response_types=["code"],
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    # MCP's OAuth provider is an httpx2 Auth object.
    # It must be attached to httpx2.AsyncClient and then
    # passed into streamable_http_client.
    async with httpx2.AsyncClient(
        auth=oauth_provider,
        follow_redirects=True,
    ) as http_client:

        async with streamable_http_client(
            ROBINHOOD_MCP_URL,
            http_client=http_client,
        ) as (
            read_stream,
            write_stream,
        ):

            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:

                await session.initialize()

                tools = await session.list_tools()

                tool_names = {
                    tool.name
                    for tool in tools.tools
                }

                print(
                    "Available tools:",
                    sorted(tool_names),
                )

                missing = (
                    READ_ONLY_TOOLS
                    - tool_names
                )

                if missing:
                    raise RuntimeError(
                        "Robinhood MCP is missing "
                        f"required read-only tools: "
                        f"{sorted(missing)}"
                    )

                account_number = (
                    await select_agentic_account(
                        session
                    )
                )

                print(
                    "Agentic account:",
                    account_number,
                )

                portfolio_payload = (
                    await read_live_portfolio(
                        session,
                        account_number,
                    )
                )

                print_portfolio_report(
                    portfolio_payload
                )


if __name__ == "__main__":
    asyncio.run(main())