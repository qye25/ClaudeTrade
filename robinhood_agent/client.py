import asyncio
import json
import webbrowser
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import AnyUrl

from mcp import ClientSession
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthToken,
)


ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_FILE = Path.home() / ".robinhood_mcp_tokens.json"
AGENTIC_NICKNAME = "Agentic"

# Safety switch: live order execution is intentionally disabled.
LIVE_ORDER_EXECUTION = False


# Temporary instrument leverage metadata.
# We can move this into portfolio policy/instrument metadata later.
LEVERAGE_MULTIPLIERS = {
    "UPRO": Decimal("3"),
    "DFEN": Decimal("3"),
    "TSLA": Decimal("1"),
    "RKLB": Decimal("1"),
    "NFLX": Decimal("1"),
}


# Only these tools may ever be called by this client.
READ_ONLY_TOOLS = {
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_quotes",
    "get_equity_tax_lots",
    "get_equity_tradability",
}


class FileTokenStorage(TokenStorage):
    """Small local JSON token store for Robinhood MCP OAuth."""

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
            data = json.loads(self.path.read_text(encoding="utf-8"))

            if not isinstance(data, dict):
                return

            tokens = data.get("tokens")
            if tokens:
                try:
                    self._tokens = OAuthToken.model_validate(tokens)
                except Exception:
                    self._tokens = None

            client_info = data.get("client_info")
            if client_info:
                try:
                    self._client_info = OAuthClientInformationFull.model_validate(
                        client_info
                    )
                except Exception:
                    self._client_info = None

        except (OSError, json.JSONDecodeError):
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

        try:
            self.path.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )
            self.path.chmod(0o600)
        except OSError:
            # Do not expose credentials or crash because of a local
            # filesystem permission problem.
            pass

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(
        self,
        client_info: OAuthClientInformationFull,
    ) -> None:
        self._client_info = client_info
        self._save()


CALLBACK_RESULT: dict | None = None
CALLBACK_SERVER: asyncio.AbstractServer | None = None


async def _handle_callback_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle the local OAuth browser callback."""

    global CALLBACK_RESULT

    try:
        request = await reader.read(65535)
        request_text = request.decode("utf-8", errors="replace")
        lines = request_text.splitlines()

        if not lines:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        parts = lines[0].split()
        if len(parts) < 2:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        method, path = parts[0], parts[1]

        if method != "GET":
            writer.write(
                b"HTTP/1.1 405 Method Not Allowed\r\n"
                b"Connection: close\r\n\r\n"
            )
            await writer.drain()
            return

        parsed = urlparse(path)
        query = parse_qs(parsed.query)

        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        iss = query.get("iss", [None])[0]

        if code:
            CALLBACK_RESULT = {
                "code": code,
                "state": state,
                "iss": iss,
            }

            body = (
                "<html><body>"
                "<h1>Authorization complete</h1>"
                "<p>You can close this window and return to ClaudeTrade.</p>"
                "</body></html>"
            ).encode()

            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Connection: close\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
        else:
            body = (
                "<html><body>"
                "<h1>Authorization failed</h1>"
                "<p>No authorization code was returned.</p>"
                "</body></html>"
            ).encode()

            response = (
                b"HTTP/1.1 400 Bad Request\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Connection: close\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )

        writer.write(response)
        await writer.drain()

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_callback_server() -> asyncio.AbstractServer:
    """Start the localhost OAuth callback server."""

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
    """Fallback OAuth URL used by the browser redirect handler."""

    return (
        f"{ROBINHOOD_MCP_URL}"
        "/authorize?redirect_uri=http://localhost:8765/callback"
    )


async def redirect_handler(authorization_url: str) -> None:
    """Open the authorization URL in the user's browser."""

    webbrowser.open(authorization_url)

    print()
    print("Open the browser window for Robinhood authentication.")
    print(authorization_url)
    print()


async def callback_handler() -> AuthorizationCodeResult:
    """Wait for the local OAuth callback."""

    global CALLBACK_RESULT

    await start_callback_server()

    deadline = asyncio.get_running_loop().time() + 180

    while CALLBACK_RESULT is None:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(
                "Timed out waiting for Robinhood OAuth callback."
            )

        await asyncio.sleep(0.25)

    result = CALLBACK_RESULT
    CALLBACK_RESULT = None

    return AuthorizationCodeResult(
        code=result["code"],
        state=result.get("state"),
        iss=result.get("iss"),
    )


def _money(value) -> Decimal:
    """Convert a value to a two-decimal Decimal."""

    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


async def call_read_only(
    session: ClientSession,
    name: str,
    arguments: dict | None = None,
):
    """
    Call a Robinhood MCP tool only if it is explicitly read-only.

    This is the primary safety boundary of the client.
    """

    if name not in READ_ONLY_TOOLS:
        raise RuntimeError(
            f"BLOCKED: {name} is not in the read-only allowlist."
        )

    if LIVE_ORDER_EXECUTION:
        raise RuntimeError(
            "LIVE_ORDER_EXECUTION must remain False for this client."
        )

    return await session.call_tool(
        name,
        arguments or {},
    )


def extract_data(result) -> dict:
    """
    Extract structured MCP data.

    Robinhood's MCP response may expose structured content in slightly
    different wrappers, so accept the common dictionary forms.
    """

    content = getattr(result, "structured_content", None)

    if isinstance(content, dict):
        data = content.get("data", content)

        if isinstance(data, dict):
            return data

    raise RuntimeError(
        f"Unexpected MCP response shape: {content!r}"
    )


async def select_agentic_account(
    session: ClientSession,
) -> str:
    """Select the Robinhood account enabled for agentic access."""

    result = await call_read_only(
        session,
        "get_accounts",
        {},
    )

    data = extract_data(result)

    accounts = data.get("accounts", data.get("results", []))

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
            "No Robinhood account with agentic_allowed=True was found."
        )

    # Prefer the explicitly named Agentic account if present.
    named = [
        account
        for account in eligible
        if account.get("nickname") == AGENTIC_NICKNAME
        or account.get("name") == AGENTIC_NICKNAME
    ]

    account = named[0] if named else eligible[0]

    account_number = (
        account.get("account_number")
        or account.get("accountNumber")
    )

    if not account_number:
        raise RuntimeError(
            "Selected Agentic account is missing an account_number."
        )

    return str(account_number)


def extract_symbols(positions: dict) -> list[str]:
    """Extract unique equity symbols from Robinhood positions."""

    rows = positions.get("positions", [])

    if not isinstance(rows, list):
        raise RuntimeError(
            f"Unexpected positions payload: {rows!r}"
        )

    symbols: list[str] = []
    seen: set[str] = set()

    for position in rows:
        if not isinstance(position, dict):
            continue

        symbol = str(position.get("symbol", "")).strip().upper()

        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)

    return symbols


def normalize_portfolio(
    portfolio: dict,
    positions: dict,
    quotes: dict,
) -> dict:
    """
    Produce a deterministic normalized representation.

    This remains separate from Portfolio.from_robinhood_payload() for
    backward compatibility with the existing CLI output.
    """

    portfolio_value = Decimal(
        str(
            portfolio.get("portfolio_value")
            or portfolio.get("equity")
            or portfolio.get("total_equity")
            or 0
        )
    )

    buying_power = Decimal(
        str(
            portfolio.get("buying_power")
            or 0
        )
    )

    quote_rows = quotes.get("quotes", quotes.get("results", []))

    if isinstance(quote_rows, dict):
        quote_rows = list(quote_rows.values())

    quote_map: dict[str, Decimal] = {}

    if isinstance(quote_rows, list):
        for quote in quote_rows:
            if not isinstance(quote, dict):
                continue

            symbol = str(
                quote.get("symbol", "")
            ).strip().upper()

            price = (
                quote.get("price")
                or quote.get("last_price")
                or quote.get("lastTradePrice")
            )

            if symbol and price is not None:
                try:
                    quote_map[symbol] = Decimal(str(price))
                except Exception:
                    continue

    normalized_positions: dict[str, dict] = {}

    for position in positions.get("positions", []):
        if not isinstance(position, dict):
            continue

        symbol = str(
            position.get("symbol", "")
        ).strip().upper()

        if not symbol:
            continue

        quantity = Decimal(
            str(position.get("quantity", 0))
        )

        last_price = quote_map.get(
            symbol,
            Decimal(str(position.get("last_price", 0))),
        )

        market_value_raw = position.get("market_value")

        if market_value_raw is None:
            market_value = quantity * last_price
        else:
            market_value = Decimal(str(market_value_raw))

        weight = (
            market_value / portfolio_value
            if portfolio_value
            else Decimal("0")
        )

        leverage = LEVERAGE_MULTIPLIERS.get(
            symbol,
            Decimal("1"),
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
                (weight * leverage).quantize(
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
    session: ClientSession,
    account_number: str,
    symbols: list[str],
) -> dict[str, list]:
    """Read tax lots for every dynamically discovered symbol."""

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
            or data.get("results")
            or []
        )

        if isinstance(rows, dict):
            rows = [rows]

        if not isinstance(rows, list):
            raise RuntimeError(
                f"Unexpected tax-lot payload for {symbol}: {rows!r}"
            )

        results[symbol] = rows

    return results

def flatten_tax_lots(
    tax_lots_by_symbol: dict[str, list],
) -> dict:
    """Convert symbol-keyed tax lots into Portfolio model format."""

    lots = []

    for symbol, rows in tax_lots_by_symbol.items():
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            lot = dict(row)

            # Ensure every lot has a symbol.
            lot.setdefault("symbol", symbol)

            lots.append(lot)

    return {"lots": lots}

async def read_live_portfolio(
    session: ClientSession,
    account_number: str,
) -> dict:
    """
    Read the complete current Robinhood equity portfolio.

    Symbol discovery is based on the actual positions response. There is
    deliberately no benchmark-symbol list here.
    """

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

    portfolio = extract_data(portfolio_result)
    positions = extract_data(positions_result)

    symbols = extract_symbols(positions)

    if symbols:
        quotes_result = await call_read_only(
            session,
            "get_equity_quotes",
            {
                "account_number": account_number,
                "symbols": symbols,
            },
        )

        quotes = extract_data(quotes_result)

        tax_lots = await read_live_tax_lots(
            session,
            account_number,
            symbols,
        )
    else:
        quotes = {"quotes": []}
        tax_lots = {}

    normalized = normalize_portfolio(
        portfolio,
        positions,
        quotes,
    )

    return {
        "portfolio": portfolio,
        "positions": positions,
        "quotes": quotes,
        "tax_lots": flatten_tax_lots(tax_lots),
        "normalized": normalized,
        "symbols": symbols,
    }


async def main():
    """Connect to Robinhood MCP and print a read-only portfolio snapshot."""

    storage = FileTokenStorage(TOKEN_FILE)

    oauth_provider = OAuthClientProvider(
        server_url=ROBINHOOD_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="ClaudeTrade Robinhood Read-Only Client",
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
            scope=None,
        ),
        storage=storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )

    async with httpx.AsyncClient(
        auth=oauth_provider,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            ROBINHOOD_MCP_URL,
            http_client=http_client,
        ) as (read_stream, write_stream):
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

                if "get_accounts" not in tool_names:
                    raise RuntimeError(
                        "Robinhood MCP did not expose get_accounts."
                    )

                account_number = await select_agentic_account(
                    session
                )

                # Do not print the account number itself.
                print("Selected Robinhood Agentic account.")

                portfolio_payload = await read_live_portfolio(
                    session,
                    account_number,
                )

                print()
                print("Discovered symbols:")
                print(
                    json.dumps(
                        portfolio_payload["symbols"],
                        indent=2,
                    )
                )

                print()
                print("Normalized portfolio:")
                print(
                    json.dumps(
                        portfolio_payload["normalized"],
                        indent=2,
                        default=str,
                    )
                )

                print()
                print("Tax lots:")
                print(
                    json.dumps(
                        portfolio_payload["tax_lots"],
                        indent=2,
                        default=str,
                    )
                )


if __name__ == "__main__":
    asyncio.run(main())