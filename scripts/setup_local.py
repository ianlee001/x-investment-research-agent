"""Install an isolated PostgreSQL 17 on Windows; never changes system services."""

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
PG = RUNTIME / "pgsql"
DATA = RUNTIME / "pgdata"
# PostgreSQL.org -> EDB Windows binaries -> PostgreSQL 17.11 x64.
PG_URL = "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260616"


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sec-email", default="")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("Use docker compose on Linux/macOS, or supply DATABASE_URL.")
    RUNTIME.mkdir(exist_ok=True)
    if not (PG / "bin" / "postgres.exe").exists():
        archive = RUNTIME / "postgresql-17.11.zip"
        if not archive.exists():
            print("Downloading PostgreSQL 17.11 from EDB...", flush=True)
            temporary = archive.with_suffix(".download")
            with httpx.stream("GET", PG_URL, follow_redirects=True, timeout=90) as response:
                response.raise_for_status()
                with temporary.open("wb") as handle:
                    for data in response.iter_bytes(1024 * 1024):
                        handle.write(data)
            temporary.replace(archive)
        digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
        (RUNTIME / "postgresql-download.sha256").write_text(digest, encoding="utf-8")
        with zipfile.ZipFile(archive) as package:
            for entry in package.infolist():
                target = (RUNTIME / entry.filename).resolve()
                if not target.is_relative_to(RUNTIME.resolve()):
                    raise ValueError("Unsafe archive entry")
                # No pgAdmin/StackBuilder needed for the local database runtime.
                if entry.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                    package.extract(entry, RUNTIME)
        print("Database binaries extracted.", flush=True)
    local_env = ROOT / ".env.local"
    config = dict(dotenv_values(local_env)) if local_env.exists() else {}
    if "DATABASE_URL" not in config:
        password = secrets.token_hex(24)
        config["DATABASE_URL"] = f"postgresql://xresearch:{password}@127.0.0.1:55432/xresearch"
    else:
        from urllib.parse import urlsplit

        password = urlsplit(config["DATABASE_URL"]).password
    if args.sec_email:
        if "@" not in args.sec_email or any(c in args.sec_email for c in '\n\r"'):
            raise ValueError("Invalid contact email")
        config["SEC_USER_AGENT"] = f"XInvestmentResearch/1.0 {args.sec_email}"
    local_env.write_text("".join(f'{key}="{value}"\n' for key, value in config.items()), encoding="utf-8")
    password_file = RUNTIME / ".pg-password"
    if not (DATA / "PG_VERSION").exists():
        password_file.write_text(password, encoding="utf-8")
        try:
            run(
                PG / "bin/initdb.exe",
                "-D",
                DATA,
                "-U",
                "xresearch",
                "--pwfile",
                password_file,
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            )
        finally:
            password_file.unlink(missing_ok=True)
        with (DATA / "postgresql.conf").open("a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\ntimezone = 'UTC'\n")
    status = subprocess.run([str(PG / "bin/pg_ctl.exe"), "-D", str(DATA), "status"], capture_output=True)
    if status.returncode != 0:
        # pg_ctl launches a daemon; CREATE_NO_WINDOW avoids a visible console helper.
        run(
            PG / "bin/pg_ctl.exe",
            "-D",
            DATA,
            "-l",
            RUNTIME / "postgres.log",
            "-w",
            "start",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    env = {**os.environ, "PGPASSWORD": password}
    exists = subprocess.run(
        [
            str(PG / "bin/psql.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            "55432",
            "-U",
            "xresearch",
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname='xresearch'",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    if "1" not in exists.stdout:
        run(
            PG / "bin/createdb.exe", "-h", "127.0.0.1", "-p", "55432", "-U", "xresearch", "xresearch", env=env
        )
    print("PostgreSQL ready on 127.0.0.1:55432; credentials saved only in .env.local.")


if __name__ == "__main__":
    main()
