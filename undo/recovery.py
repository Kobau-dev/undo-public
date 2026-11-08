"""Built-in recovery playbooks: the click paths each app already offers to bring work back.

The agent still drives the UI with visible clicks, but it walks a short, known path (an app's own undo history,
autosave, recently-closed list, trash or version history) instead of re-creating the work by hand.
Playbooks are injected into the Analyzer prompt (so it picks the right strategy) and into the executor task.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Playbook:
    name: str
    apps: tuple[str, ...]  # lowercase substrings of the foreground app name
    steps: str
    titles: tuple[str, ...] = ()  # lowercase substrings of the window title (web apps inside a browser)
    exact_apps: tuple[str, ...] = ()  # lowercase full app names too generic for substring matching ("code")

    def matches(self, app: str = "", title: str = "") -> bool:
        app, title = (app or "").lower(), (title or "").lower()
        return app in self.exact_apps or any(a in app for a in self.apps) or any(t in title for t in self.titles)


PLAYBOOKS: tuple[Playbook, ...] = (
    Playbook(
        "Blender",
        ("blender",),
        """\
- Still open, recent mistake: Edit > Undo History, then click the last step BEFORE the mistake
  (more precise than repeated Cmd+Z). Cmd+Shift+Z redoes. The list is newest first; a state applies instantly,
  so never "wait" after clicking one: if the scene did not change, you missed the row, reopen the list.
- Edit > Undo History opens the list of steps to the RIGHT of the Edit menu as soon as "Undo History" is
  clicked or hovered. When that list is on screen, never click "Undo History" again: click a row of the list.
- Objects deleted a while ago but the work done SINCE must be kept (going back would lose it): copy them from
  the past. 1) Edit > Undo History, click the row directly BELOW "Delete" in that list (the list is newest first;
  that row is usually "Select": the objects are back and already selected, highlighted in orange). 2) The mouse
  already rests over the 3D viewport after that click: just press Cmd+C (no click). 3) Edit > Undo History, click the
  FIRST row at the very top of the list (the latest step: everything done since comes back). 4) Press Cmd+V
  right away (no click): the objects reappear at their exact place, highlighted in orange; that is the end,
  call done. While in the past state never click in the viewport or the outliner (a new action there erases all
  the later steps); to close a menu press Esc, never click in the scene.
- Blender was closed or crashed: File > Recover > Last Session (reopens the scene as it was when Blender quit).
- Unsaved work lost, older state needed: File > Recover > Auto Save..., pick the most recent autosave
  (sort by date), then click "Recover Auto Save".
- File saved over by mistake: File > Open, select the same name ending in .blend1 (previous save), Open.
- To bring back only one object from an older file: File > Append, open that .blend, double-click Object,
  select the object, click Append.
- Prefer menus and dialogs. Never drag in the 3D viewport. If Blender asks to save the current file before
  opening another one, use ask_user.""",
    ),
    Playbook(
        "Web browser",
        ("chrome", "brave", "safari", "firefox", "arc", "edge", "opera", "vivaldi"),
        """\
- Closed tab or window: Cmd+Shift+T (repeat to go further back), or History > Recently Closed.
- Page navigated away: Cmd+[ (Back). Form contents are often still there after Back.
- Older page: History > Show All History (Cmd+Y in Chrome/Brave), search by title, click it.""",
    ),
    Playbook(
        "Google Docs / Sheets / Slides",
        (),
        """\
- File > Version history > See version history (Cmd+Option+Shift+H), click the version just before the
  mistake, then "Restore this version".""",
        titles=("google docs", "google sheets", "google slides"),
    ),
    Playbook(
        "Notion",
        ("notion",),
        """\
- Deleted page: Trash in the left sidebar, search the page, click the restore arrow.
- Changed content: page "..." menu (top right) > Page history (or Version history), pick the version, Restore.""",
    ),
    Playbook(
        "Figma",
        ("figma",),
        """\
- File > Show version history, click the version before the mistake, then "Restore this version" in its menu.""",
    ),
    Playbook(
        "Finder",
        ("finder",),
        """\
- File just deleted: Cmd+Z in Finder puts it back.
- Older deletion: open the Trash (Dock), right-click the file > Put Back.""",
    ),
    Playbook(
        "Apple Notes",
        (),
        """\
- Deleted note: open the "Recently Deleted" folder in the sidebar, drag the note back to Notes
  (or select it and use Edit > Undo right after the deletion).""",
        exact_apps=("notes", "apple notes"),
    ),
    Playbook(
        "Apple documents (Pages, Numbers, Keynote, TextEdit, Preview)",
        (),
        """\
- File > Revert To > Browse All Versions..., go back to the version before the mistake, click Restore.""",
        exact_apps=("pages", "numbers", "keynote", "textedit", "preview"),
    ),
    Playbook(
        "Code editors (VS Code, Cursor)",
        ("visual studio code", "cursor"),
        """\
- Closed editor tab: Cmd+Shift+T.
- Lost changes in a file: Explorer > Timeline (bottom of the sidebar) shows Local History; click the entry
  before the mistake, then "Restore Contents" from its right-click menu.""",
        exact_apps=("code",),
    ),
)


def playbooks_for(windows: list[tuple[str, str]]) -> list[Playbook]:
    """Playbooks for any of the (app, window title) pairs, in PLAYBOOKS order, without duplicates."""
    return [p for p in PLAYBOOKS if any(p.matches(a, t) for a, t in windows)]


def recovery_hints(windows: list[tuple[str, str]]) -> str:
    """Text block for prompts; empty when no known app is involved."""
    found = playbooks_for(windows)
    if not found:
        return ""
    return "\n\n".join(f"Built-in recovery for {p.name}:\n{p.steps}" for p in found)
