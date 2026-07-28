# Hades Menu Designer

Visual UI editor for Hades modding. Extracts sprites from the game's
.pkg files (vendored deppth2, subtextures mode) and provides a
1920x1080 stage matching the game's screen coordinate space for
mocking up menus, saved as .hmd.json project files.

## Running
python main.py
(Missing dependencies are detected on startup with an offer to install.)

## Current features
- Batch extraction of a Packages folder (skips 720p/BC3 duplicates,
  caches results per package)
- Single .pkg extraction and cached-package dropdown
- Searchable sprite thumbnail browser
- Stage: double-click to place, drag, wheel zoom, rubber-band select
- Arrows nudge 1px, Shift+arrows 10px, Delete, Ctrl+D duplicate,
  PageUp/PageDown draw order
- Layers panel: select sync, rename (Lua-identifier enforced),
  drag to reorder, lock checkbox
- File menu: New/Open/Save/Save As (.hmd.json)
- Edit menu: Undo (Ctrl+Z), Redo (Ctrl+Y), Delete
- Selection outline, locked layers refuse drag and nudge

## Layout
- main.py       window, panels, menus, handlers
- stage.py      the 1920x1080 stage and sprite items
- assets.py     sprite index, extraction workers
- records.py    component records, project save/load, undo stack
- vendor/       deppth2 (MIT), see LICENSE-NOTE.txt
