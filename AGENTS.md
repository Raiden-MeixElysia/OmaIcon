# OmaIcon

An Omarchy bar plugin, id `raiden-meixelysia.omaicon`, that switches icon packs. It ships the OmaPixIcon pixel pack. The pack's source of truth is the separate [OmaPixIcon](https://github.com/Raiden-MeixElysia/OmaPixIcon) repo; this repo only carries a pinned copy.

## Layout

- `manifest.json`: the plugin manifest at the repo root. `omarchy plugin add` clones the repo whole. Entry point `plugin/Panel.qml`.
- `plugin/`: the panel (Quickshell QML). It runs `../engine/omaicon.py` with `python3 -B`, so no `__pycache__` lands in the plugin folder and reloads it.
- `engine/omaicon.py`: the only code that switches icon pack or palette. The panel, the theme-switch hook and OmaPixIcon's `install.sh` all call it. It logs every step to stderr as `omaicon: …`.
- `pack/`: the OmaPixIcon renderer and data, copied by `tools/sync-pack.sh`. Never edit it here. `pack/SOURCE` is `<sha> <date>` of the last OmaPixIcon commit that changed `data/`.

## State on a user's machine

Nothing is written until the user picks a pack. Then:

- `~/.local/share/icons/OmaPixIcon/`: the rendered pack. Each render goes into a new `scalable-<hash>` folder.
- `~/.icons/omaicon-shell-<n>/apps/`: the chosen pack as the Omarchy shell sees it. See below.
- `~/.config/omaicon/config`: `ICON_THEME` (`omarchy` when unset, `OmaPixIcon`, or any installed pack), `PALETTE`, `RESTART_SHELL`, `DESKTOP_FIX` (see Launchers).
- `~/.config/omarchy/hooks/theme-set.d/50-omaicon`: runs `omaicon.py theme-set`; deletes itself once the plugin is gone.
- `~/.cache/omaicon/`: preview SVGs for the panel.
- `~/.local/share/omaicon/pack/`: `data/` and `SOURCE` fetched by `update-pack`. `active_pack()` uses it when its date beats `pack/SOURCE`; `render.ROOT` points at the active one.

## Why the shell needs its own copy

The Omarchy dock, launcher and menu ignore the GTK icon theme. `AppLibrary.qml` scans every icon dir (`~/.icons` first), keeps the first file per name, and prefers SVG over PNG. So `publish()` in `omaicon.py` resolves the chosen pack the GTK way (pack, `Inherits`, hicolor, pixmaps), links each name into a new `~/.icons/omaicon-shell-<n>/apps/`, wraps PNGs that an SVG elsewhere would beat, and gives launcher names the pack lacks its `application-x-executable`. A new folder per switch makes the shell reload the images.

## Launchers

An app whose launcher says `Icon=/path/icon.png` can't follow a pack. `fix_launchers()` in `omaicon.py` rewrites that line to the pack's icon name, but only for `ICON_THEME=OmaPixIcon` and `DESKTOP_FIX=1`. OmaPixIcon's `install.sh` sets it; with no value it counts as on only if `~/.local/state/omapix/desktop-backup/` exists, so earlier installs keep working. A launcher in `/usr/share/applications` gets an override copy marked `X-OmaPix-Override=true`; one in `~/.local/share/applications` is edited in place after a backup.

Apps rewrite their launcher on update, so one pass at install time isn't enough. `fix-launchers` runs from `apply()` and from `plugin/Panel.qml` whenever the shell's `DesktopEntries.applications` list changes (debounced, and once at start). It must stay idempotent, writing only launchers still on a path, because its own writes change that list. Don't call `refresh()` from it: `refresh()` adds a launcher, which would loop. `remove()` undoes it all.

## Pack updates

`omaicon.py update-pack` (the button at the end of OmaPixIcon's palette strip) is the plugin's only network access. It fetches data only, from fixed GitHub URLs pinned to one commit, with size limits and timeouts, and `check_icons`/`check_themes` reject anything that could escape a folder or break the renderer. Never fetch or run code. A renderer change ships through `tools/sync-pack.sh` and a plugin release.

## Rules

- Never write to the user's icons, hooks or settings before they pick a pack. The marketplace forbids changing configuration without consent.
- Every switch goes through `apply()`: gsettings for apps, `publish()` for the shell, then the hook.
- Panel text binds as `Text.PlainText`. Pack names come from files on disk.
- Shell refresh order: `icons.revision` when the shell watches it, else a hidden launcher, else a shell restart. `RESTART_SHELL` overrides.
- Test the panel by looking at it: `omarchy-shell raiden-meixelysia.omaicon open`, then `grim`. Its log lines start with `omaicon:` in `quickshell log --path /usr/share/omarchy/shell`.
- Run tests against a throwaway `HOME`, and pass that `HOME` to every command, hooks included.
