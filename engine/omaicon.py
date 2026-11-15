#!/usr/bin/env python3
"""usage:
  omaicon.py status
  omaicon.py use <icon-theme|omarchy>
  omaicon.py palette <name>
  omaicon.py theme-set
  omaicon.py refresh
  omaicon.py update-pack
  omaicon.py fix-launchers
  omaicon.py remove"""
import base64, glob, hashlib, json, os, re, shutil, struct, subprocess, sys, time, urllib.error, urllib.request
from datetime import datetime

BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pack')
sys.path.insert(0, os.path.join(BUNDLED, 'engine'))
import render
from render import HOUSE, THEME_NAME, build_theme, read_colors_toml, resolve_palette, svg, theme_palette

HOME = os.path.expanduser('~')
FETCHED = os.path.join(HOME, '.local/share/omaicon/pack')
PACK_REPO = 'Raiden-MeixElysia/OmaPixIcon'
CONF = os.path.join(HOME, '.config/omaicon/config')
THEME_DIR = os.path.join(HOME, '.local/share/icons', THEME_NAME)
OMARCHY_THEME = os.path.join(HOME, '.local/state/omarchy/current/theme')
REVISION = os.path.join(HOME, '.local/state/omarchy/current/icons.revision')
APPS = os.path.join(HOME, '.local/share/applications')
BACKUP = os.path.join(HOME, '.local/state/omapix/desktop-backup')
SHELL_ICONS = os.path.join(HOME, '.icons')
SHELL_PREFIX = 'omaicon-shell-'
APP_DIR = re.compile(r'(^|/)(apps|devices)(/|$)')
CACHE = os.path.join(HOME, '.cache/omaicon/palettes')
PIXEL_CACHE = os.path.join(HOME, '.cache/omaicon/previews')
HOOK = os.path.join(HOME, '.config/omarchy/hooks/theme-set.d/50-omaicon')
FOLLOW = 'omarchy'
PREVIEWS = [
    ['system-file-manager', 'org.gnome.Nautilus', 'folder'],
    ['utilities-terminal', 'org.gnome.Console', 'foot', 'Alacritty'],
    ['web-browser', 'firefox', 'chromium', 'google-chrome'],
    ['accessories-text-editor', 'org.gnome.TextEditor', 'text-editor'],
    ['preferences-system', 'org.gnome.Settings', 'preferences-desktop'],
]
PALETTE_ICON = 'gpick'


def log(msg):
    print(f'omaicon: {msg}', file=sys.stderr, flush=True)


# ------------------------------------------------------------------ pack data
def pack_source(root):
    path = os.path.join(root, 'SOURCE')
    if not os.path.exists(path):
        return '', None
    sha, _, date = open(path, encoding='utf-8').read().strip().partition(' ')
    return sha, datetime.fromisoformat(date) if date else None


def active_pack():
    # The newer of the bundled pack and one fetched by update-pack.
    if not os.path.exists(os.path.join(FETCHED, 'SOURCE')):
        return BUNDLED
    bundled, fetched = pack_source(BUNDLED)[1], pack_source(FETCHED)[1]
    return FETCHED if bundled is None or fetched > bundled else BUNDLED


ROOT = render.ROOT = active_pack()


# ------------------------------------------------------------------ config
def read_conf():
    conf = {}
    if os.path.exists(CONF):
        for line in open(CONF, encoding='utf-8'):
            key, sep, value = line.strip().partition('=')
            if sep:
                conf[key] = value
    return conf


def write_conf(**values):
    lines = open(CONF, encoding='utf-8').read().splitlines() if os.path.exists(CONF) else []
    for key, value in values.items():
        row = f'{key}={value}'
        hit = [i for i, line in enumerate(lines) if line.startswith(key + '=')]
        if hit:
            lines[hit[-1]] = row
        else:
            lines.append(row)
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    log(f'config {values}')


def choice(conf):
    return conf.get('ICON_THEME') or FOLLOW


def palette(conf):
    return conf.get('PALETTE') or 'sync'


# ------------------------------------------------------------------ icon themes
def icon_roots():
    data_home = os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local/share')
    data_dirs = (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')
    return [os.path.join(data_home, 'icons'), os.path.join(HOME, '.icons')] + [os.path.join(d, 'icons') for d in data_dirs if d]


def read_index(path):
    keys, section = {}, None
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('['):
            section = line
        elif section == '[Icon Theme]' and '=' in line:
            key, _, value = line.partition('=')
            keys.setdefault(key.strip(), value.strip())
    return keys


def installed_themes():
    themes = {}
    for root in icon_roots():
        for index in sorted(glob.glob(os.path.join(root, '*', 'index.theme'))):
            name = os.path.basename(os.path.dirname(index))
            if name in themes:
                themes[name]['roots'].append(os.path.dirname(index))
                continue
            keys = read_index(index)
            if not keys.get('Directories'):
                continue
            themes[name] = {
                'name': name,
                'title': keys.get('Name') or name,
                'dir': os.path.dirname(index),
                'roots': [os.path.dirname(index)],
                'hidden': keys.get('Hidden', '').lower() == 'true',
                'inherits': [t for t in keys.get('Inherits', '').split(',') if t],
                'dirs': [d for d in keys['Directories'].split(',') if d],
            }
    return themes


def dir_size(sub):
    head = sub.split('/')[0].split('x')[0]
    return int(head) if head.isdigit() else 1024


def own_icon(theme, wanted):
    best = None
    for root in theme['roots']:
        for sub in theme['dirs']:
            for ext in ('svg', 'png'):
                path = os.path.join(root, sub, f'{wanted}.{ext}')
                if os.path.exists(path):
                    rank = (ext == 'svg', dir_size(sub))
                    if best is None or rank > best[0]:
                        best = (rank, path)
    return best[1] if best else None


def find_icon(themes, name, group, seen):
    theme = themes.get(name)
    if not theme or name in seen or name == 'hicolor':
        return None
    seen.add(name)
    for wanted in group:
        hit = own_icon(theme, wanted)
        if hit:
            return hit
    for parent in theme['inherits']:
        hit = find_icon(themes, parent, group, seen)
        if hit:
            return hit
    return None


def previews(themes, name):
    hits = (find_icon(themes, name, group, set()) for group in PREVIEWS)
    return [hit for hit in hits if hit]


def theme_icons(theme):
    best = {}
    for root in theme['roots']:
        for sub in filter(APP_DIR.search, theme['dirs']):
            folder = os.path.join(root, sub)
            if not os.path.isdir(folder):
                continue
            for file in os.listdir(folder):
                stem, ext = os.path.splitext(file)
                rank = (ext == '.svg', dir_size(sub))
                if ext in ('.svg', '.png') and (stem not in best or rank > best[stem][0]):
                    best[stem] = (rank, os.path.join(folder, file))
    return {stem: hit[1] for stem, hit in best.items()}


def chain(themes, name, seen):
    if name in seen or name not in themes:
        return []
    seen.add(name)
    return [name] + [t for parent in themes[name]['inherits'] for t in chain(themes, parent, seen)]


def lookup_order(themes, target):
    order = chain(themes, target, set())
    if 'hicolor' not in order and 'hicolor' in themes:
        order.append('hicolor')
    return order


def resolve_all(themes, order):
    pixmaps = glob.glob('/usr/share/pixmaps/*.png') + glob.glob('/usr/share/pixmaps/*.svg')
    icons = {os.path.splitext(os.path.basename(f))[0]: f for f in pixmaps}
    for name in reversed(order):
        icons.update(theme_icons(themes[name]))
    log(f'resolved {len(icons)} icons through {" > ".join(order)}')
    return icons


def omarchy_icons():
    path = os.path.join(OMARCHY_THEME, 'icons.theme')
    return open(path, encoding='utf-8').readline().strip() if os.path.exists(path) else 'Yaru-blue'


# ------------------------------------------------------------------ palettes
def palette_names():
    themes = json.load(open(os.path.join(ROOT, 'data', 'omarchy-themes.json')))
    return ['sync', 'house', 'dmg'] + sorted(themes)


def palette_map(name):
    if name == 'sync':
        colors = os.path.join(OMARCHY_THEME, 'colors.toml')
        return theme_palette(read_colors_toml(colors)) if os.path.exists(colors) else resolve_palette('house')
    return resolve_palette(name)


def pixel_previews(conf):
    icons = json.load(open(os.path.join(ROOT, 'data', 'icons.json')))
    by_name = {n: v for v in icons.values() for n in v['names']}
    pal = palette_map(palette(conf))
    tag = hashlib.sha256(json.dumps(pal, sort_keys=True).encode()).hexdigest()[:8]
    os.makedirs(PIXEL_CACHE, exist_ok=True)
    keep = []
    for group in PREVIEWS:
        name = next((n for n in group if n in by_name), None)
        if not name:
            continue
        path = os.path.join(PIXEL_CACHE, f'{name}-{tag}.svg')
        if not os.path.exists(path):
            with open(path, 'w') as f:
                f.write(svg(by_name[name]['rows'], pal))
        keep.append(path)
    for stale in glob.glob(os.path.join(PIXEL_CACHE, '*')):
        if stale not in keep:
            os.remove(stale)
    return keep


def palette_previews():
    rows = json.load(open(os.path.join(ROOT, 'data', 'icons.json')))[PALETTE_ICON]['rows']
    os.makedirs(CACHE, exist_ok=True)
    keep, out = set(), []
    for name in palette_names():
        pal = palette_map(name)
        tag = hashlib.sha256(json.dumps(pal, sort_keys=True).encode()).hexdigest()[:8]
        path = os.path.join(CACHE, f'{PALETTE_ICON}-{name}-{tag}.svg')
        if not os.path.exists(path):
            with open(path, 'w') as f:
                f.write(svg(rows, pal))
        keep.add(path)
        out.append({'name': name, 'preview': path})
    for stale in glob.glob(os.path.join(CACHE, '*')):
        if stale not in keep:
            os.remove(stale)
    return out


# ------------------------------------------------------------------ apply
def gsettings_get():
    out = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'icon-theme'],
                         check=True, capture_output=True, text=True).stdout
    return out.strip().strip("'")


def gsettings_set(name):
    subprocess.run(['gsettings', 'set', 'org.gnome.desktop.interface', 'icon-theme', name], check=True)
    log(f'icon-theme {name}')


def render_theme(conf):
    # Not `render`: that would shadow the render module, and update_pack's render.ROOT would miss it.
    name = palette(conf)
    inherit = omarchy_icons()
    new = THEME_DIR + '.new'
    shutil.rmtree(new, ignore_errors=True)
    n, total = build_theme(new, palette_map(name), f'{inherit},Yaru,Adwaita,hicolor', label=name)
    shutil.rmtree(THEME_DIR, ignore_errors=True)
    os.rename(new, THEME_DIR)
    log(f'rendered {n} icons / {total} names, palette {name}, inherits {inherit}')
    return inherit


def apply(conf):
    target = choice(conf)
    if target == THEME_NAME:
        inherit = render_theme(conf)
        if gsettings_get() == THEME_NAME:
            # GTK repaints only on a name change.
            gsettings_set(inherit)
            time.sleep(0.3)
        theme = THEME_NAME
    else:
        theme = omarchy_icons() if target == FOLLOW else target
        check(theme)
    gsettings_set(theme)
    fix_launchers(conf)
    publish(theme)
    write_hook()
    refresh(conf)


def write_hook():
    os.makedirs(os.path.dirname(HOOK), exist_ok=True)
    engine = os.path.abspath(__file__)
    with open(HOOK, 'w') as f:
        f.write(f'#!/bin/bash\n# Written by OmaIcon\nE={json.dumps(engine)}\n'
                '[[ -f $E ]] || { rm -f "$0"; exit 0; }\nexec python3 -B "$E" theme-set\n')
    os.chmod(HOOK, 0o755)


def remove():
    conf = read_conf()
    restore_launchers()
    for path in [HOOK, THEME_DIR, os.path.dirname(CONF), os.path.dirname(CACHE), os.path.dirname(FETCHED)] + glob.glob(os.path.join(SHELL_ICONS, SHELL_PREFIX + '*')):
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
        log(f'removed {path}')
    if os.path.isdir(SHELL_ICONS) and not os.listdir(SHELL_ICONS):
        os.rmdir(SHELL_ICONS)
    gsettings_set(omarchy_icons())
    refresh(conf)


def shell_svgs():
    roots = [SHELL_ICONS] + icon_roots()
    names = set()
    for root in dict.fromkeys(roots):
        for folder, subs, files in os.walk(root, followlinks=False):
            subs[:] = [d for d in subs if not d.startswith(SHELL_PREFIX)]
            if '/apps' in folder or '/devices' in folder:
                names.update(f[:-4] for f in files if f.endswith('.svg'))
    return names


def png_svg(path):
    data = open(path, 'rb').read()
    w, h = struct.unpack('>II', data[16:24])
    href = 'data:image/png;base64,' + base64.b64encode(data).decode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" xlink:href="{href}"/></svg>')


def desktop_icon(path):
    if not os.path.exists(path):
        return ''
    group = ''
    for line in open(path, encoding='utf-8', errors='replace'):
        if line.startswith('['):
            group = line.strip()
        elif group == '[Desktop Entry]' and line.startswith('Icon='):
            return line[5:].strip()
    return ''


def launcher_names():
    data_home = os.environ.get('XDG_DATA_HOME') or os.path.join(HOME, '.local/share')
    data_dirs = (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':')
    names = set()
    for d in [data_home] + [d for d in data_dirs if d]:
        for f in glob.glob(os.path.join(d, 'applications', '*.desktop')):
            name = desktop_icon(f)
            if name and not name.startswith('/'):
                names.add(name)
    return names


def launcher_icons():
    # Names the desktop fix gave launchers, mapped to their own files.
    pairs = [(os.path.join(APPS, os.path.basename(b)), b) for b in glob.glob(os.path.join(BACKUP, '*.desktop'))]
    for f in glob.glob(os.path.join(APPS, '*.desktop')):
        if OVERRIDE in open(f, encoding='utf-8', errors='replace').read():
            pairs.append((f, os.path.join('/usr/share/applications', os.path.basename(f))))
    out = {}
    for current, original in pairs:
        name, path = desktop_icon(current), desktop_icon(original)
        if name and not name.startswith('/') and path.endswith(('.svg', '.png')) and os.path.exists(path):
            out[name] = path
    return out


# ------------------------------------------------------------------ launchers
# Apps that hard-code an icon file path in their launcher (`Icon=/opt/app/icon.png`) can't follow the pack.
# Point them at the pack's icon name instead. Apps rewrite their launcher on update, so this runs on every
# apply() and whenever the shell's app list changes. It only touches launchers still on a path, so it settles.
OVERRIDE = 'X-OmaPix-Override=true'
HASHED = re.compile(r'\.h[0-9a-f]{12,}$')


def launcher_fix_enabled(conf):
    # Opt-in: install.sh sets DESKTOP_FIX=1. Installs that already ran its fix (it made BACKUP) keep it on.
    default = '1' if os.path.isdir(BACKUP) else '0'
    return choice(conf) == THEME_NAME and conf.get('DESKTOP_FIX', default) == '1'


def pack_names():
    with open(os.path.join(ROOT, 'data', 'icons.json'), encoding='utf-8') as f:
        return {n for v in json.load(f).values() for n in v['names']}


def launcher_icon_name(path, icon, names):
    stem = os.path.basename(path)[:-len('.desktop')]
    # Per-install launchers carry a hash suffix: com.xd.cindy.user.h69297e92b23bcb60
    candidates = (stem, stem.lower(), HASHED.sub('', stem), os.path.splitext(os.path.basename(icon))[0],
                  stem.removesuffix('-desktop'))
    return next((n for n in candidates if n in names), '')


def write_launcher(src, dst, name, override):
    lines, group, done = [], '', False
    with open(src, encoding='utf-8', errors='surrogateescape') as f:
        for line in f.read().splitlines():
            if line.startswith('['):
                group = line.strip()
            if not done and group == '[Desktop Entry]' and line.startswith('Icon='):
                lines.append(f'Icon={name}')
                if override:
                    lines.append(OVERRIDE)
                done = True
            else:
                lines.append(line)
    tmp = dst + '.omaicon-tmp'
    with open(tmp, 'w', encoding='utf-8', errors='surrogateescape') as f:
        f.write('\n'.join(lines) + '\n')
    shutil.copymode(src, tmp)
    os.replace(tmp, dst)


def fix_launchers(conf):
    if not launcher_fix_enabled(conf):
        return
    names = pack_names()
    own = {os.path.basename(f) for f in glob.glob(os.path.join(APPS, '*.desktop'))}
    fixed = 0
    for f in sorted(glob.glob('/usr/share/applications/*.desktop')) + sorted(glob.glob(os.path.join(APPS, '*.desktop'))):
        base, icon = os.path.basename(f), desktop_icon(f)
        name = launcher_icon_name(f, icon, names) if icon.startswith('/') else ''
        if not name:
            continue
        if os.path.dirname(f) == APPS:
            # The app just wrote this file, so it is the original to keep.
            os.makedirs(BACKUP, exist_ok=True)
            shutil.copyfile(f, os.path.join(BACKUP, base))
            write_launcher(f, f, name, False)
        elif base not in own:
            os.makedirs(APPS, exist_ok=True)
            write_launcher(f, os.path.join(APPS, base), name, True)
        else:
            continue
        fixed += 1
    if fixed:
        log(f're-pointed {fixed} launcher(s) that hard-code an icon path')


def restore_launchers():
    for f in glob.glob(os.path.join(APPS, '*.desktop')):
        if OVERRIDE in open(f, encoding='utf-8', errors='replace').read():
            os.remove(f)
    for b in glob.glob(os.path.join(BACKUP, '*.desktop')):
        target = os.path.join(APPS, os.path.basename(b))
        # A launcher the app has rewritten since is newer than the backup.
        if os.path.exists(target) and not desktop_icon(target).startswith('/'):
            shutil.copyfile(b, target)
    shutil.rmtree(BACKUP, ignore_errors=True)


def publish(theme):
    # The shell keeps the first file per name: SVG, ~/.icons first.
    themes = installed_themes()
    order = lookup_order(themes, theme)
    icons = resolve_all(themes, order)
    for name, path in launcher_icons().items():
        icons.setdefault(name, path)
    # GTK shows the generic icon for names the theme lacks.
    generic = next(filter(None, (own_icon(themes[t], 'application-x-executable') for t in order)), None)
    if not generic:
        sys.exit(f'omaicon: {theme} has no application-x-executable icon')
    missing = launcher_names() - icons.keys()
    for name in missing:
        icons[name] = generic
    svgs = shell_svgs()
    out = os.path.join(SHELL_ICONS, f'{SHELL_PREFIX}{time.time_ns()}', 'apps')
    os.makedirs(out)
    wrapped = 0
    for stem, path in icons.items():
        if path.endswith('.png') and stem in svgs:
            with open(os.path.join(out, stem + '.svg'), 'w') as f:
                f.write(png_svg(path))
            wrapped += 1
        else:
            os.symlink(path, os.path.join(out, stem + os.path.splitext(path)[1]))
    for old in glob.glob(os.path.join(SHELL_ICONS, SHELL_PREFIX + '*')):
        if old != os.path.dirname(out):
            shutil.rmtree(old)
    log(f'published {len(icons)} icons of {theme} to {os.path.dirname(out)}: {len(missing)} generic, {wrapped} PNG wrapped')


def check(target):
    if target not in (THEME_NAME, FOLLOW) and target not in installed_themes():
        sys.exit(f'omaicon: icon theme {target} is not installed')


def refresh(conf):
    mode = conf.get('RESTART_SHELL') or 'auto'
    shell = os.path.join(os.environ.get('OMARCHY_PATH') or '/usr/share/omarchy', 'shell/services/AppLibrary.qml')
    library = open(shell, encoding='utf-8').read() if os.path.exists(shell) else ''
    if mode != 'always' and 'icons.revision' in library:
        os.makedirs(os.path.dirname(REVISION), exist_ok=True)
        with open(REVISION, 'w') as f:
            f.write(f'{time.time_ns() // 1000}\n')
        log('refresh: icons.revision')
        return
    if mode == 'always' or (mode == 'auto' and 'target: DesktopEntries.applications' not in library):
        restart = shutil.which('omarchy-restart-shell')
        if not restart:
            sys.exit('omaicon: refresh needs omarchy-restart-shell, which is missing')
        subprocess.Popen([restart], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        log('refresh: shell restart')
        return
    # The shell rescans its icon index on app-list changes.
    os.makedirs(APPS, exist_ok=True)
    launcher = os.path.join(APPS, f'omaicon-refresh-{os.getpid()}.desktop')
    with open(launcher, 'w') as f:
        f.write('[Desktop Entry]\nType=Application\nName=OmaIcon refresh\nExec=true\nNoDisplay=true\n')
    subprocess.Popen(['sh', '-c', 'sleep 2; rm -f "$1"', 'sh', launcher],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    log('refresh: hidden launcher')


# ------------------------------------------------------------------ commands
# ------------------------------------------------------------------ pack update
SLOTS = set(HOUSE) | {'.', '%'}
COLOR_KEYS = {'foreground', 'background', 'dark_background', 'darker_background', 'light_foreground',
              'red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'magenta', 'brown', 'accent'}


def fetch(url, limit, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': 'OmaIcon'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except (urllib.error.URLError, TimeoutError) as e:
        sys.exit(f'omaicon: fetch {url}: {e}')
    if len(data) > limit:
        sys.exit(f'omaicon: {url} is over {limit} bytes')
    log(f'fetched {url} ({len(data)} bytes)')
    return data


def bad(what):
    sys.exit(f'omaicon: refusing the new pack: {what}')


def check_icons(icons):
    if not isinstance(icons, dict) or not 0 < len(icons) <= 50000:
        bad('icons.json is not a map of icons')
    if PALETTE_ICON not in icons:
        bad(f'icons.json lacks {PALETTE_ICON}')
    for iid, v in icons.items():
        if not isinstance(v, dict):
            bad(f'{iid} is not an icon')
        rows, names = v.get('rows'), v.get('names')
        if not isinstance(rows, list) or not 8 <= len(rows) <= 256:
            bad(f'{iid}: rows')
        if any(not isinstance(row, str) or len(row) != len(rows) or not set(row) <= SLOTS for row in rows):
            bad(f'{iid}: rows must be square and use palette slots')
        if not isinstance(names, list) or not 0 < len(names) <= 500:
            bad(f'{iid}: names')
        for n in names:
            # Names become file names.
            if not isinstance(n, str) or not 0 < len(n) <= 200 or n.startswith('.') or '/' in n or '\0' in n:
                bad(f'{iid}: name {n!r}')
        if not re.fullmatch(r'[a-z]{1,32}', str(v.get('context', 'apps'))):
            bad(f'{iid}: context')


def check_themes(themes):
    if not isinstance(themes, dict) or not 0 < len(themes) <= 500:
        bad('omarchy-themes.json is not a map of themes')
    for name, colors in themes.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name) or not isinstance(colors, dict):
            bad(f'theme {name!r}')
        for key, value in colors.items():
            if not isinstance(value, str) or len(value) > 128:
                bad(f'{name}.{key}')
            if (key in COLOR_KEYS or key.startswith('bright_')) and not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                bad(f'{name}.{key} is not a #rrggbb colour')


def update_pack():
    global ROOT
    api = f'https://api.github.com/repos/{PACK_REPO}/commits?path=data&per_page=1'
    head = json.loads(fetch(api, 1 << 20, 20))
    sha, date = head[0]['sha'], head[0]['commit']['committer']['date']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        bad(f'commit {sha!r}')
    latest = datetime.fromisoformat(date)
    current_sha, current = pack_source(ROOT)
    if sha == current_sha or (current is not None and current >= latest):
        log(f'OmaPixIcon is up to date at {current_sha[:7]} ({date})')
        return
    raw = f'https://raw.githubusercontent.com/{PACK_REPO}/{sha}/data'
    icons_raw = fetch(f'{raw}/icons.json', 64 << 20, 120)
    themes_raw = fetch(f'{raw}/omarchy-themes.json', 2 << 20, 30)
    icons, themes = json.loads(icons_raw), json.loads(themes_raw)
    check_icons(icons)
    check_themes(themes)
    stage = FETCHED + '.new'
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(os.path.join(stage, 'data'))
    with open(os.path.join(stage, 'data', 'icons.json'), 'wb') as f:
        f.write(icons_raw)
    with open(os.path.join(stage, 'data', 'omarchy-themes.json'), 'wb') as f:
        f.write(themes_raw)
    with open(os.path.join(stage, 'SOURCE'), 'w') as f:
        f.write(f'{sha} {date}\n')
    shutil.rmtree(FETCHED, ignore_errors=True)
    os.rename(stage, FETCHED)
    ROOT = render.ROOT = active_pack()
    log(f'OmaPixIcon updated to {sha[:7]} ({date}): {len(icons)} icons, {len(themes)} palettes')
    conf = read_conf()
    if choice(conf) == THEME_NAME:
        apply(conf)


def status():
    conf = read_conf()
    themes = installed_themes()
    follow = omarchy_icons()
    sha, date = pack_source(ROOT)
    rows = []
    if follow in themes:
        rows.append({'name': FOLLOW, 'title': 'Omarchy', 'previews': previews(themes, follow)})
    rows.append({'name': THEME_NAME, 'title': THEME_NAME, 'previews': pixel_previews(conf)})
    for name, theme in sorted(themes.items(), key=lambda t: t[1]['title'].lower()):
        if not theme['hidden'] and name not in (follow, THEME_NAME):
            rows.append({'name': name, 'title': theme['title'], 'previews': previews(themes, name)})
    json.dump({
        'choice': choice(conf),
        'current': gsettings_get(),
        'palette': palette(conf),
        'pack': {'sha': sha[:7], 'date': date.isoformat() if date else ''},
        'themes': rows,
        'palettes': palette_previews(),
    }, sys.stdout)


def main():
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ('', [])
    if cmd == 'status' and not args:
        status()
    elif cmd == 'use' and len(args) == 1:
        check(args[0])
        write_conf(ICON_THEME=args[0])
        apply(read_conf())
    elif cmd == 'palette' and len(args) == 1:
        if args[0] not in palette_names():
            sys.exit(f'omaicon: unknown palette {args[0]}')
        write_conf(PALETTE=args[0], ICON_THEME=THEME_NAME)
        apply(read_conf())
    elif cmd == 'theme-set' and not args:
        apply(read_conf())
    elif cmd == 'refresh' and not args:
        refresh(read_conf())
    elif cmd == 'update-pack' and not args:
        update_pack()
    elif cmd == 'fix-launchers' and not args:
        fix_launchers(read_conf())
    elif cmd == 'remove' and not args:
        remove()
    else:
        sys.exit(__doc__.strip())


if __name__ == '__main__':
    main()
