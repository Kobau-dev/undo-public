"""Command line: python -m undo <command>."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from undo.config import Settings
from undo.log import console, get_logger, setup_logging

log = get_logger("cli")


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--model", help="Holo model id (default from UNDO_MODEL or holo4-35b-a3b)")
    p.add_argument("--data-dir", help="recording folder (default ~/.undo)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="undo", description="Undo keeps a history of what happened on your Mac, and can act on it")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="recorder + hotkey + overlay (the full product)")
    run.add_argument("--dry-run", action="store_true", help="print actions instead of executing them")
    run.add_argument("--executor", choices=["native", "holo-agent"], help="native loop (default) or H Agents API desktop agent")
    run.add_argument("--no-ui", action="store_true", help="console instead of the floating overlay")
    run.add_argument("--request", help="skip the hotkey/voice step and run this request once (useful for testing)")
    run.add_argument("--yes", action="store_true", help="auto-confirm sensitive actions (console UI only)")
    _common(run)

    rec = sub.add_parser("record", help="recorder only")
    _common(rec)

    an = sub.add_parser("analyze", help="run the Analyzer only")
    an.add_argument("request")
    an.add_argument("--replay", metavar="DIR", help="folder created by `undo export`")
    an.add_argument("--execute", action="store_true", help="also run the executor on the result")
    an.add_argument("--dry-run", action="store_true")
    _common(an)

    ex = sub.add_parser("export", help="save the last minutes of recording for --replay")
    ex.add_argument("out_dir")
    ex.add_argument("--minutes", type=int)
    _common(ex)

    demo = sub.add_parser("demo", help="serve the demo web apps")
    demo.add_argument("--port", type=int, default=8765)

    sub.add_parser("models", help="list Holo models available with your key")
    sub.add_parser("menubar", help="macOS menu bar icon (rumps)")
    st = sub.add_parser("status", help="recorder statistics")
    _common(st)
    return p


def _settings(args) -> Settings:
    s = Settings()
    if getattr(args, "model", None):
        s.model = args.model
    if getattr(args, "data_dir", None):
        s.data_dir = Path(args.data_dir).expanduser()
    if getattr(args, "dry_run", False):
        s.dry_run = True
    if getattr(args, "executor", None):
        s.executor_backend = args.executor
    return s


def _missing_h_key() -> int:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    todo = "add it to" if env_file.exists() else "run `cp .env.example .env`, then add it to"
    console.print(f"[red]H_API_KEY is missing[/] — {todo} {env_file} (get a key: https://hub.hcompany.ai/)", soft_wrap=True)
    return 2


def cmd_run(args) -> int:
    settings = _settings(args)
    if not settings.h_api_key:
        return _missing_h_key()

    from undo.app import UndoApp
    from undo.permissions import missing_permissions
    from undo.providers import build_transcriber
    from undo.ui.overlay import build_ui

    missing = missing_permissions()
    if missing:
        console.print(f"[yellow]macOS permissions missing:[/] {', '.join(missing)} — allow your terminal in System Settings → Privacy & Security, quit it (⌘Q), reopen it and run this again", soft_wrap=True)
    if not settings.gladia_api_key:
        console.print("[yellow]GLADIA_API_KEY is not set[/] — no voice: you will type your request in the bubble (get a key: https://app.gladia.io/)", soft_wrap=True)
    ui = build_ui(no_ui=args.no_ui or bool(args.request), auto_confirm=args.yes, hotkey=settings.hotkey)
    app = UndoApp(settings, ui, transcriber=build_transcriber(settings))
    if settings.dry_run:
        console.print("[yellow]dry-run: actions will be printed, not executed[/]")

    def worker():
        if args.request:
            app.recorder.start()
            time.sleep(1.0)  # at least one 'current' frame
            app.handle_request(args.request)
            app.shutdown()
            ui.quit()
        else:
            app.run_forever()

    try:
        ui.start(worker)
    except KeyboardInterrupt:
        app.shutdown()
    return 0


def cmd_record(args) -> int:
    from undo.recorder import Recorder

    settings = _settings(args)
    rec = Recorder(settings)
    rec.start()
    try:
        while True:
            time.sleep(10)
            log.info("recorder: %s", rec.stats())
    except KeyboardInterrupt:
        rec.stop()
    return 0


def cmd_analyze(args) -> int:
    from undo.analyzer import Analyzer
    from undo.providers import build_vision
    from undo.recorder import FrameIndex

    settings = _settings(args)
    now, base = None, None
    if args.replay:
        base = Path(args.replay).expanduser()
        index = FrameIndex(base / "frames.db")
        latest = index.latest(1)
        if not latest:
            console.print(f"[red]no frames in {base}[/]")
            return 2
        now = latest[0].ts + 1
        settings.lookback_minutes = max(settings.lookback_minutes, settings.buffer_minutes)
    else:
        index = FrameIndex(settings.db_path)
    try:
        fallback = build_vision(settings)
    except Exception:
        fallback = None
    analyzer = Analyzer(settings, build_vision(settings, role="analyzer"), index, base_dir=base, fallback=fallback)
    analysis = analyzer.analyze(args.request, now=now)
    console.print_json(analysis.model_dump_json())
    if args.execute:
        from undo.executor import AgentExecutor
        from undo.ui.console import ConsoleUI

        result = AgentExecutor(settings, build_vision(settings), ui=ConsoleUI()).run(analysis, args.request)
        console.print_json(result.model_dump_json())
        return 0 if result.success else 1
    return 0


def cmd_export(args) -> int:
    from undo.app import export_recording

    out = export_recording(_settings(args), Path(args.out_dir).expanduser(), args.minutes)
    console.print(f"exported to {out} — replay with: undo analyze --replay {out} \"…\"")
    return 0


def cmd_demo(args) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "demo"))
    from serve import serve  # type: ignore

    serve(args.port)
    return 0


def cmd_models(args) -> int:
    from undo.providers import build_vision

    settings = Settings()
    vision = build_vision(settings)
    for m in vision.list_models():
        console.print(("[green]*[/] " if m == settings.model else "  ") + m)
    return 0


def cmd_menubar(args) -> int:
    from undo.ui.menubar import main as menubar_main

    menubar_main(Settings())
    return 0


def cmd_status(args) -> int:
    from undo.recorder import FrameIndex

    settings = _settings(args)
    index = FrameIndex(settings.db_path)
    latest = index.latest(1)
    console.print_json(json.dumps({"frames": index.count(), "apps": index.apps(time.time() - 3600), "latest": latest[0].model_dump() if latest else None, "data_dir": str(settings.data_dir)}, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(getattr(args, "verbose", False))
    from undo.providers import MissingHKey

    handlers = {"run": cmd_run, "record": cmd_record, "analyze": cmd_analyze, "export": cmd_export, "demo": cmd_demo, "models": cmd_models, "menubar": cmd_menubar, "status": cmd_status}
    try:
        return handlers[args.cmd](args)
    except MissingHKey:
        return _missing_h_key()


if __name__ == "__main__":
    sys.exit(main())
