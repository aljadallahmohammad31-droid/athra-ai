# ATHRA AI - persistent Gemini configuration

1. Open the `.env` file in the same folder as `app.py`.
2. Put your NEW Gemini API key after `GEMINI_API_KEY=`. Do not add spaces around `=`.
3. Save the file.
4. Stop ATHRA if it is already running, then start it again with `START_NASJ.bat` or `run_nasj.cmd`.
5. Open http://127.0.0.1:8765 and try Ask ATHRA AI.

The app reads `.env` automatically at startup using Python's standard library; no extra package is required. A key already set in the terminal takes precedence over `.env`. The real `.env` is excluded by `.gitignore`; do not share it or include it in public ZIPs.

Security: any API key pasted into a chat or shared file should be revoked and replaced. Keep the replacement private.
