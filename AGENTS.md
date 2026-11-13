# OmaIcon

An Omarchy bar plugin, id `raiden-meixelysia.omaicon`, that switches icon packs. It ships the OmaPixIcon pixel pack. The pack's source of truth is the separate [OmaPixIcon](https://github.com/Raiden-MeixElysia/OmaPixIcon) repo; this repo only carries a pinned copy.

## Layout

- `manifest.json`: the plugin manifest at the repo root. `omarchy plugin add` clones the repo whole. Entry point `plugin/Panel.qml`.
- `plugin/`: the panel (Quickshell QML). It runs `../engine/omaicon.py` with `python3 -B`, so no `__pycache__` lands in the plugin folder and reloads it.
- `engine/omaicon.py`: the only code that switches icon pack or palette. The panel, the theme-switch hook and OmaPixIcon's `install.sh` all call it. It logs every step to stderr as `omaicon: …`.
- `pack/`: the OmaPixIcon renderer and data, copied by `tools/sync-pack.sh`. Never edit it here; `pack/SOURCE` is the OmaPixIcon commit it came from.

## State on a user's machine

Nothing is written until the user picks a pack. Then:

- `~/.local/share/icons/OmaPixIcon/`: the rendered pack. Each render goes into a new `scalable-<hash>` folder.
- `~/.icons/omaicon-shell-<n>/apps/`: the chosen pack as the Omarchy shell sees it. See below.
- `~/.config/omaicon/config`: `ICON_THEME` (`omarchy` when unset, `OmaPixIcon`, or any installed pack), `PALETTE`, `RESTART_SHELL`.
- `~/.config/omarchy/hooks/theme-set.d/50-omaicon`: runs `omaicon.py theme-set`; deletes itself once the plugin is gone.
- `~/.cache/omaicon/`: preview SVGs for the panel.

## Why the shell needs its own copy

The Omarchy dock, launcher and menu ignore the GTK icon theme. `AppLibrary.qml` scans every icon dir (`~/.icons` first), keeps the first file per name, and prefers SVG over PNG. So `publish()` in `omaicon.py` resolves the chosen pack the GTK way (pack, `Inherits`, hicolor, pixmaps), links each name into a new `~/.icons/omaicon-shell-<n>/apps/`, wraps PNGs that an SVG elsewhere would beat, and gives launcher names the pack lacks its `application-x-executable`. A new folder per switch makes the shell reload the images.

## Rules

- Never write to the user's icons, hooks or settings before they pick a pack. The marketplace forbids changing configuration without consent.
- Every switch goes through `apply()`: gsettings for apps, `publish()` for the shell, then the hook.
- Panel text binds as `Text.PlainText`. Pack names come from files on disk.
- Shell refresh order: `icons.revision` when the shell watches it, else a hidden launcher, else a shell restart. `RESTART_SHELL` overrides.
- Test the panel by looking at it: `omarchy-shell raiden-meixelysia.omaicon open`, then `grim`. Its log lines start with `omaicon:` in `quickshell log --path /usr/share/omarchy/shell`.
- Run tests against a throwaway `HOME`, and pass that `HOME` to every command, hooks included.
