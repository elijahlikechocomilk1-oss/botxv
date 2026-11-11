# RevealR Discord Bot

A prefix-command Discord bot that wraps the included `RevealR.luau` engine.

## Commands

- `.log` or `.l` — runs RevealR against an attached `.lua` / `.luau` file and sends the generated dump back as an attachment.
- `.beautify lua` / `.beautify luau` — formats Lua/Luau with StyLua.
- `.beautify javascript` / `.beautify nodejs` — formats JavaScript with Prettier.
- `.beautify python` — formats Python with Black.
- `.ping` — reports bot latency.
- `.help` — lists commands.

For `.log` and `.beautify`, attach a text/code file to the command. Inline code after the command is also accepted. Maximum file size defaults to 8 MB.

## Setup (Linux / Termux)

1. Install Python 3.10+ and Lune. Follow the official Lune installation instructions: <https://lune-org.github.io/docs>.
2. Install Python dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

3. Install formatters you want to use:

   ```sh
   cargo install stylua
   npm install -g prettier
   python -m pip install black
   ```

   StyLua requires Rust/Cargo; Prettier requires Node.js/npm. These are optional per language.

4. Create your Discord application and bot in the Discord Developer Portal. Enable **Message Content Intent** under Bot → Privileged Gateway Intents, then invite the bot with permission to view channels, send messages, and attach files.
5. Copy `.env.example` to `.env` and put your bot token in `DISCORD_TOKEN`.
6. Start it:

   ```sh
   python bot.py
   ```

## Notes

- Keep `.env` private. Never share your bot token or commit `.env`.
- The bot does not execute uploaded files as ordinary Python/Node processes. `.log` passes the input to the bundled RevealR/Lune analysis engine; review the engine and only process files you have permission to analyze.
- Run the bot in a trusted server and keep Discord permissions limited.
- The Windows `lune.exe` from the original archive is not included; install a Lune build appropriate for your operating system.
