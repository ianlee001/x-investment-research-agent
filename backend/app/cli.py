import argparse
import asyncio
import logging
import sys


def main():
    parser = argparse.ArgumentParser(prog="xresearch")
    parser.add_argument("command", choices=["api", "worker", "mcp", "init"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("httpx", "httpx2", "httpcore", "openai", "mcp", "fastmcp", "mcp.client.streamable_http"):
        logging.getLogger(name).setLevel(logging.WARNING)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.command == "api":
        import uvicorn

        from app.config import get_settings

        config = get_settings()
        # Running the coroutine preserves the selector loop required by psycopg on Windows.
        asyncio.run(
            uvicorn.Server(
                uvicorn.Config(
                    "app.api:app",
                    host=config.app_host,
                    port=config.app_port,
                    loop="asyncio",
                    access_log=False,
                )
            ).serve()
        )
    elif args.command == "worker":
        from app.worker import run_worker

        asyncio.run(run_worker())
    elif args.command == "mcp":
        from app.mcp_server import build_server
        from app.providers.http import ProviderHTTP

        build_server(ProviderHTTP()).run(transport="stdio")
    elif args.command == "init":
        from alembic import command
        from alembic.config import Config

        from app.config import ROOT

        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


if __name__ == "__main__":
    main()
