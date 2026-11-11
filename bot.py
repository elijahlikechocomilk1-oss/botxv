from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
PREFIX = os.getenv("BOT_PREFIX", ".")
MAX_BYTES = int(os.getenv("MAX_FILE_MB", "8")) * 1024 * 1024
ROOT = Path(__file__).resolve().parent
ENGINE = ROOT / "RevealR.luau"
LUNE = os.getenv("LUNE_BIN", "lune")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned_or(PREFIX), intents=intents, help_command=None)


def safe_name(name: str, fallback: str = "script.lua") -> str:
    name = Path(name or fallback).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", name) or fallback


async def get_source(ctx: commands.Context, *, text: str = "") -> tuple[str, str]:
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if attachment.size > MAX_BYTES:
            raise ValueError(f"File is too large. Maximum: {MAX_BYTES // (1024 * 1024)} MB.")
        data = await attachment.read()
        try:
            return data.decode("utf-8-sig"), safe_name(attachment.filename)
        except UnicodeDecodeError as exc:
            raise ValueError("Please upload a UTF-8 text/code file.") from exc
    if text.strip():
        return text.strip(), "input.lua"
    raise ValueError("Attach a code file or include code after the command.")


async def run_process(*args: str, timeout: int = 120) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError("Processing timed out.")
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | prefix: {PREFIX}")


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.reply(f"Pong! `{round(bot.latency * 1000)} ms`", mention_author=False)


@bot.command(name="log", aliases=["l"])
@commands.max_concurrency(1, per=commands.BucketType.user, wait=False)
async def log_dump(ctx: commands.Context, *, inline_code: str = ""):
    """Analyze a Lua/Luau file with the bundled RevealR engine."""
    if not shutil.which(LUNE) and not Path(LUNE).exists():
        await ctx.reply("Lune runtime wasn't found. Install Lune and set `LUNE_BIN` if needed. See README.md.", mention_author=False)
        return
    if not ENGINE.is_file():
        await ctx.reply("RevealR.luau is missing from the bot folder.", mention_author=False)
        return
    try:
        source, original_name = await get_source(ctx, text=inline_code)
    except ValueError as exc:
        await ctx.reply(str(exc), mention_author=False)
        return

    if len(source.encode()) > MAX_BYTES:
        await ctx.reply(f"Input exceeds the {MAX_BYTES // (1024 * 1024)} MB limit.", mention_author=False)
        return

    async with ctx.typing():
        with tempfile.TemporaryDirectory(prefix="revealr_") as temp:
            input_path = Path(temp) / safe_name(original_name)
            output_path = Path(temp) / (input_path.stem + "_dump.lua")
            input_path.write_text(source, encoding="utf-8")
            try:
                code, stdout, stderr = await run_process(LUNE, "run", str(ENGINE), str(input_path), str(output_path))
            except (RuntimeError, OSError) as exc:
                await ctx.reply(f"RevealR failed: `{exc}`", mention_author=False)
                return
            if output_path.is_file() and output_path.stat().st_size:
                await ctx.reply(
                    content="**RevealR analysis complete.** Output attached below.",
                    file=discord.File(output_path, filename=safe_name(input_path.stem + "_dump.lua")),
                    mention_author=False,
                )
            else:
                detail = (stderr or stdout or f"Process exited with code {code}").strip()
                detail = detail[-1400:]
                await ctx.reply(f"**RevealR did not produce an output file.**\n```text\n{detail}\n```", mention_author=False)


@bot.command(name="beautify")
async def beautify(ctx: commands.Context, language: str = "", *, inline_code: str = ""):
    """Format source with StyLua, Prettier, or Black."""
    language = language.lower().strip()
    aliases = {"luau": "lua", "node": "javascript", "js": "javascript", "py": "python"}
    language = aliases.get(language, language)
    supported = {"lua", "javascript", "typescript", "python"}
    if language not in supported:
        await ctx.reply("Usage: `.beautify <lua|luau|javascript|nodejs|python>` plus a code attachment or inline code.", mention_author=False)
        return
    try:
        source, original_name = await get_source(ctx, text=inline_code)
    except ValueError as exc:
        await ctx.reply(str(exc), mention_author=False)
        return
    if len(source.encode()) > MAX_BYTES:
        await ctx.reply(f"Input exceeds the {MAX_BYTES // (1024 * 1024)} MB limit.", mention_author=False)
        return

    formatter = {"lua": "stylua", "javascript": "prettier", "typescript": "prettier", "python": "black"}[language]
    executable = shutil.which(formatter)
    if not executable:
        await ctx.reply(f"Formatter `{formatter}` isn't installed. Install it using the README instructions.", mention_author=False)
        return

    suffix = {"lua": ".lua", "javascript": ".js", "typescript": ".ts", "python": ".py"}[language]
    with tempfile.TemporaryDirectory(prefix="beautify_") as temp:
        path = Path(temp) / (Path(original_name).stem + suffix)
        path.write_text(source, encoding="utf-8")
        if language == "python":
            args = [executable, "--quiet", str(path)]
        elif language in {"javascript", "typescript"}:
            args = [executable, "--write", "--single-quote", str(path)]
        else:
            args = [executable, "--indent-type", "Spaces", "--indent-width", "4", str(path)]
        async with ctx.typing():
            try:
                code, stdout, stderr = await run_process(*args, timeout=60)
            except (RuntimeError, OSError) as exc:
                await ctx.reply(f"Formatter failed: `{exc}`", mention_author=False)
                return
        if code != 0:
            await ctx.reply(f"**Could not beautify this file.**\n```text\n{(stderr or stdout)[-1200:]}\n```", mention_author=False)
            return
        if not path.is_file():
            await ctx.reply("Formatter did not produce an output file.", mention_author=False)
            return
        await ctx.reply(
            content=f"**Beautified {language} code.**",
            file=discord.File(path, filename=safe_name(Path(original_name).stem + "_beautified" + suffix)),
            mention_author=False,
        )


@bot.command(name="help")
async def help_command(ctx: commands.Context):
    await ctx.reply(
        "**RevealR Bot**\n"
        "`.log` / `.l` — analyze an attached Lua/Luau file with RevealR\n"
        "`.beautify <language>` — format Lua/Luau, JavaScript/Node.js, or Python\n"
        "`.ping` — show bot latency\n\n"
        "Attach a source file to `.log` or `.beautify`. Inline code also works.",
        mention_author=False,
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MaxConcurrencyReached):
        await ctx.reply("Your previous `.log` request is still running. Try again shortly.", mention_author=False)
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply("Missing argument. Try `.help` for command usage.", mention_author=False)
    else:
        print(f"Command error: {error!r}")
        await ctx.reply("Something went wrong while processing that command.", mention_author=False)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in your .env file first.")
    bot.run(TOKEN)
