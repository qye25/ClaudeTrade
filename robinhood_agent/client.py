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
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

ROBINHOOD_MCP_URL = "https://agent.robinhood.com/mcp/trading"
TOKEN_FILE = Path.home() / ".robinhood_mcp_tokens.json"
AGENTIC_NICKNAME = "Agentic"
LIVE_ORDER_EXECUTION = False

LEVERAGE_MULTIPLIERS = {
    "UPRO": Decimal("3"),
    "DFEN": Decimal("3"),
    "TSLA": Decimal("1"),
    "RKLB": Decimal("1"),
    "NFLX": Decimal("1"),
}

READ_ONLY_TOOLS = {
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_quotes",
    "get_equity    "get_equity    "get_equity    "get_equity    "geFi    "get_equit(TokenStorage):
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: OAuthToken | None = None
        self._client_info: OAuthClientIn        seull | None = None
                                                                            exists():
                                                        loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                tokens = data.get("tokens")
                if tokens:
                                                                                        ta.get("client_info")
                if client_info:
                     elf._cli                 lientInformationFull(**client_info)                Exception:
            pass

    def _save(self) -> None:
        data = {
            "tokens": sel            "tokeump(mode="json") if self._tokens else None,
            "client_info": self._client_info.model_dump(mode="json") if self._client_info else None,
        }
        self.path.write_text(json.dumps(d        self.path.write_text(json.dumps(d        se        self.path.chmod(0o600)
        except OSError:
            pass

    async def get_tokens(self) -> OAuthToken | None:
        return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens = tokens
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self._client_info

    async def set_client_info(self, client_inf    async def set_client_info(self, client_inf    async def set_client_info(self, client_inf    asyn


CALLBACK_RESULT: dict | None = None
CALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCALCAESULT, CALLBACK_SERVER

    request = await reader.read(65535)
    request_te    request_te    request_te    request_te    request_te    requplitlines()
    if not lines:
        writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        await writer.drain()
        writ        writ        writ        writ        writ        writ        writ        writ        writ        writ       st_line.split()
    if len(parts  < 3:
        writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        await writer.drain()
                                          r.wait_closed()
        return

    method, path, _ = parts
    if metho    if metho    if metho    if metho    if metho    if metho    if\r\n\    if metho    if mewriter.drain(    if metho    if metho    if metho    if metho    if metho    if metho    if\r\n\    if metho    if mewriter.drain(    if metho    if me  code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]

    if code:
        CALLBACK_RESULT = {"code": code, "state": state}
        body = "<html><body><h1>Authorization complete</h1><p>You can close this window and return to the app.</p></body>".encode()
        writ r.write(b"HTTP/1.        writ r.write(b"HTTP/1.        writ r.write(b"H: {len(body)}\r\n".encode())
        writer.write(b"Content-Type: text/html; charset=utf-8\r\n")
        writer.write(b"Connection: close\r\n\r\n")
        writer.write(bod        writer.w     CALLBACK_RESULT = None
        body = "<html><body><h1>Authoriza        body = "<htmo code was returned.</p></body>".encode()
        writer.write(b"HT   1.1 400 Bad R        writer.write   write        writer.write(b"HT   1.1 400 Bad R        writer.write   write        writer.write(b"HT   1.1 400 Bad R        writer.write   write        writer.write(b"HT   1.1 400 Bad R        writer.write   write        writer.write(b"HT   1.1 400 Bad R        writer.write   write        writer.wALLBACK        writer.write(b"HT   1.1 400 Bad ACK_SERVER.wait_closed()
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
    return f"{ROBINHOOD_MCP_URL}/authorize?redirect_uri=http://localhost:8765/c    return f"{ROBINHOOD_MCP_URL}/authorize?redirect_uri=hteResult:
                                                                                            url = _oauth_url()
    webbrowser.open(url)
    print()
    print("Open the browser window for Robinhood authentication.")
    print(url)
    print()

    deadline = asyncio.get_running_loop().time() + 180
    while CALLBACK_RESULT is None:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("Timed out waiting for Robinhood OAuth callback.")
        await asyncio.sleep(0.25)

    result = CALLBACK_RESULT
    CALLBACK_RESULT = None
    return AuthorizationCodeResult(code=result["code"], state=result    return Authorizationey(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def call_read_onasyncssion, name: str, arguments: dict | None = None):
    if name not    READ_ONLY_TOOLS:
        raise RuntimeError(f"BLOCKED: {name} is not in the read-only allowlist.")
    if LIVE_ORDER_EXECUTION:
        raise RuntimeError("LIVE_ORDER_        raise RuntimeError("LIVE_ORDER_        raise RuntimeError("LIVE_ORDER_        raise RuntimeEme, arguments or {})


def extract_data(result):
    content = result.structured_content
    if not isinstance(cont   , dict):
        raise Ru        raise Ru        raise Ru        raise Rshape: {        raise Ru    a = content.get        raise Ru        raise Ru        rais        raise         raise Ru        raise Ru        raise Ru        raise Rshape: {urn data



       raise Ru     tic_account(se       raise Ru     tic_acccall_read_only(session, "get_       raise Ru     tic_account(se       raise Ru     tic_acccall_read_only(session, "get_       raise dict) else        raise Ru     tic_account(se       raise Ru     tic_acccall_reaet("accounts",       raise Ru     tic_account(se       raise Ru     tic_acccall_rear(f"Unex       raise Ru     td: {accounts!r}")

    eligible = [
        account for account in accounts
        if account.get("agentic_allowed") is True         if account.get("agentic_allowed") is True         if account.get("agentic_allowed") is True         if account.get("agentic_allowed") is True ound {len(el        if a
    account = eligible[0]
    account_number = account.get("account_number") or account.get("accountNumber")
    if not account_number:
        raise RuntimeError("Selected Agentic account is missing an account_number.")
    return account_number


def normalize_portfolio(portfolio: dict, positions: dict, quotes: dict) -> dict:
    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port    port e", quote.get("price    port    port    port   sitions = {}
    for position in positions.get("positions", []):
        symbol = str(position.get("symbol", "")).upper()
        if not symbol:
            continue
        quantity = Decimal(str(position.get("quantity", 0)))
        last_price = quote_map.get(symbol, Decimal(str(position.get("last_price", 0))))
        market_value = Decimal(str(position.get("market_value", quantity * last_price)))
        weight = market_value / portfolio_value if port   io_value else Decimal("0"        weight = market_value / portfolio_value if port   io_value else D   normalized_positions[symbol] = {
            "quantity": str(quantity),
            "last_price": str(last_price),
            "market_value": str(market_value),
            "weight": str(weight.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "leverage_multiplier": str(leverage),
            "effective_leverage_contribution": str((weight * leverage).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        }

    return {
        "portfolio_value": str(portfolio_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "buying_power": str(buying_power.quantize(Decimal("0.01"), rounding=ROUN        "buying_power": str(buying_power.quantize(ions,
    }    }    }    }    }    }    }    }    }    }    }    }    }    }    }    }[str]) -> dic    }    }    }    }    }    }    }    }    }    }    }    }    }    }mbol in symbols:
        result = await call_read_only(
            session,
            "get_equity_tax_lots",
            {"account_number": account_number, "symbol": symbol},
        )
        data = extract_        data = extract_        a.get("l        data = extract_        data = get("taxLots") or data.get("positions") or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise RuntimeError(f"Unexpected tax-lot payload for {symbol}: {rows!r}")
        results[symbol] = rows
    return results


async def read_live_portfolio(session, account_number: async def read_live_portfolio(session, account_number: async def read_live_portfcount_number": accoasync def read_live_portfolio(session, account_number: async def read_live_portfolio(session, account_number: async def read_l    quotes_result = await call_read_only(session, "get_equity_quotes", {"account_number": account_number, "symbols": ["UPRO", "TSLA", "RKLB", "NFLX", "DFEN"]})

    portfolio = extract_data(portfolio_result)
    positions = extra    positioitions_res    positions = extrtract_data(quotes_result)
    normalized = normalize_portfolio(portfolio, positions, quotes)

    return {
        "portfolio": portfolio,
        "positions": positions,
        "quotes": quotes,
        "normalized": normalized,
    }


async def main():
    storage = FileTokenStorage(TOKEN_FILE    storage = FileTokenStorageentProvider(
        server_url=ROBINHOOD_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    d MCP Local Clien            client_name="Robi    stream, write_stream) as session:
            await ses            await ses            await ses            await ses              tool_names = {tool.name for tool in tools.tools}
            print("Available tools:", sorted(tool_names))
            if "g            if "g   tool_names:
                raise Runt                raiseCP did not expose the   pected account tool.")

            account_number = await select_agentic_account(session)
                                unt_number:", account_number)
            portfolio_payload = await read_live_portfolio(session, account_number)
            print(json.dumps(portfolio_payload["normalized"], indent=2, default=str))

            tax_lots = await read_live_tax_lots(
                session,
                account_number,
                ["UPRO", "TSLA", "RKLB", "NFLX", "DFEN"],
            )
            print(json.dumps(tax_lots, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
