#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_shader_cache.py — Read-only GPU shader-cache scanner + attributor.

Scans NVIDIA DXCache/GLCache, Windows D3DSCache, and per-game Unreal PSO/shader
cache folders; reads Steam play-time records; attributes caches to games via
timestamp correlation. Prints a report. NEVER deletes anything.

Usage:
  python scan_shader_cache.py                       # human-readable report
  python scan_shader_cache.py --json                # machine-readable (JSON)
  python scan_shader_cache.py --roots E:/Program Files   # extra game roots
"""
import os
import sys
import re
import json
import glob
from collections import defaultdict
from datetime import datetime

MB = 1024 ** 2
GB = 1024 ** 3

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def human(b):
    if b >= GB:
        return f"{b / GB:,.1f} GB"
    if b >= MB:
        return f"{b / MB:,.0f} MB"
    return f"{b:,} B"


def dir_stat(path):
    total = 0
    n = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return total, n


# ----------------------------- Steam -----------------------------
def find_steam():
    import winreg
    for hive, key in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
    ]:
        try:
            k = winreg.OpenKey(hive, key)
            v, _ = winreg.QueryValueEx(k, "InstallPath")
            winreg.CloseKey(k)
            if v and os.path.isdir(v):
                return v
        except OSError:
            pass
    for cand in [r"C:\Program Files (x86)\Steam"]:
        if os.path.isdir(cand):
            return cand
    return None


def steam_library_paths(steam):
    paths = [os.path.join(steam, "steamapps")]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf):
        txt = open(vdf, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'"path"\s+"((?:[^"\\]|\\.)*)"', txt):
            p = m.group(1).replace("\\\\", "\\")
            paths.append(os.path.join(p, "steamapps"))
    seen = set()
    out = []
    for p in paths:
        p = os.path.normpath(p)
        if p not in seen and os.path.isdir(p):
            seen.add(p)
            out.append(p)
    return out


def steam_apps(libs):
    apps = {}
    for lib in libs:
        for mf in glob.glob(os.path.join(lib, "appmanifest_*.acf")):
            try:
                txt = open(mf, encoding="utf-8", errors="replace").read()
                appid = re.search(r'"appid"\s+"(\d+)"', txt)
                name = re.search(r'"name"\s+"(.*?)"', txt)
                if appid and name:
                    apps[appid.group(1)] = name.group(1)
            except OSError:
                pass
    return apps


def steam_last_played(steam):
    last = {}
    ud = os.path.join(steam, "userdata")
    if not os.path.isdir(ud):
        return last
    for uid in os.listdir(ud):
        cfg = os.path.join(ud, uid, "config", "localconfig.vdf")
        if not os.path.isfile(cfg):
            continue
        txt = open(cfg, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'"(\d+)"\s*\{[^}]*?"LastPlayed"\s*"(\d+)"', txt):
            appid, ts = m.group(1), int(m.group(2))
            if appid not in last or ts > last[appid]:
                last[appid] = ts
    return last


# ------------------------ cache scanning ------------------------
def shared_cache_locations():
    la = os.environ.get("LOCALAPPDATA", "")
    cands = [
        ("NVIDIA DXCache", os.path.join(la, "NVIDIA", "DXCache")),
        ("NVIDIA GLCache", os.path.join(la, "NVIDIA", "GLCache")),
        ("D3DSCache", os.path.join(la, "D3DSCache")),
    ]
    return [(n, p) for n, p in cands if os.path.isdir(p)]


def dxcache_analysis(path):
    files = []  # (name, size, mtime)
    for f in os.listdir(path):
        fp = os.path.join(path, f)
        if os.path.isfile(fp):
            try:
                st = os.stat(fp)
                files.append((f, st.st_size, st.st_mtime))
            except OSError:
                pass
    by_prefix = {}
    by_date = defaultdict(lambda: [0, 0])
    for name, size, mtime in files:
        p = name[:4] if len(name) >= 4 else name
        s, c, mn, mx = by_prefix.get(p, (0, 0, None, None))
        by_prefix[p] = (s + size, c + 1, min(mn, mtime) if mn else mtime,
                        max(mx, mtime) if mx else mtime)
        d = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        by_date[d][0] += size
        by_date[d][1] += 1
    return by_prefix, by_date


def find_pso_dirs(roots, min_mb=20):
    hits = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, _filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > 6:
                dirnames[:] = []
                continue
            base = os.path.basename(dirpath)
            if base in ("PSO", "ShaderCache", "PSOCache", "PipelineCache",
                        "DerivedDataCache"):
                total, n = dir_stat(dirpath)
                if total >= min_mb * MB:
                    hits[dirpath] = (total, n)
    return hits


# ------------------------ attribution ------------------------
def attribute(recent, by_date, min_mb=500):
    """recent: list of (appid, name, epoch). Returns list of
    (date, size, count, [matching game names within +-1 day])."""
    attrib = []
    for d, (size, cnt) in sorted(by_date.items()):
        if size < min_mb * MB:
            continue
        try:
            d0 = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        names = []
        for _appid, name, ts in recent:
            gd = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            try:
                delta = abs((d0 - datetime.strptime(gd, "%Y-%m-%d")).days)
            except ValueError:
                continue
            if delta <= 1:
                names.append(name)
        attrib.append((d, size, cnt, names))
    return attrib


# ---------------------------- report ----------------------------
def main():
    as_json = "--json" in sys.argv
    extra_roots = []
    if "--roots" in sys.argv:
        i = sys.argv.index("--roots")
        extra_roots = sys.argv[i + 1:]

    report = {"shared": [], "dxcache": {}, "pso": [], "steam": None,
              "recent_games": [], "attribution": []}

    # shared caches
    for name, path in shared_cache_locations():
        size, n = dir_stat(path)
        report["shared"].append({"name": name, "path": path, "size": size,
                                 "files": n})

    # DXCache analysis
    la = os.environ.get("LOCALAPPDATA", "")
    dx = os.path.join(la, "NVIDIA", "DXCache")
    if os.path.isdir(dx):
        by_prefix, by_date = dxcache_analysis(dx)
        report["dxcache"]["prefixes"] = [
            {"prefix": p, "size": v[0], "files": v[1],
             "from": datetime.fromtimestamp(v[2]).strftime("%Y-%m-%d") if v[2] else None,
             "to": datetime.fromtimestamp(v[3]).strftime("%Y-%m-%d") if v[3] else None}
            for p, v in sorted(by_prefix.items(), key=lambda kv: -kv[1][0])
        ]
        report["dxcache"]["by_date"] = [
            {"date": d, "size": v[0], "files": v[1]}
            for d, v in sorted(by_date.items())
        ]

    # Steam
    steam = find_steam()
    recent = []
    if steam:
        libs = steam_library_paths(steam)
        apps = steam_apps(libs)
        last = steam_last_played(steam)
        report["steam"] = {"path": steam, "libraries": libs}
        recent = sorted(
            [(a, apps.get(a, a), t) for a, t in last.items()],
            key=lambda x: -x[2],
        )
        report["recent_games"] = [
            {"appid": a, "name": n,
             "last_played": datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")}
            for a, n, t in recent
        ]

    # per-game PSO dirs
    roots = [la] + libs + [r for r in extra_roots if r]
    for path, (size, n) in sorted(find_pso_dirs(roots).items(),
                                  key=lambda kv: -kv[1][0]):
        report["pso"].append({"path": path, "size": size, "files": n})

    # attribution
    if os.path.isdir(dx):
        report["attribution"] = attribute(recent, dxcache_analysis(dx)[1])

    # ---- output ----
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("=" * 70)
    print("SHARED SHADER CACHES")
    print("=" * 70)
    for s in report["shared"]:
        print(f"  {s['name']:16} {human(s['size']):>10}  ({s['files']} files)")
        print(f"                  {s['path']}")

    if report["dxcache"].get("prefixes"):
        print("\nDXCache by prefix (first 4 hex chars = cache generation):")
        for p in report["dxcache"]["prefixes"]:
            rng = f"{p['from']}..{p['to']}" if p["from"] else "-"
            print(f"  {p['prefix']}  {human(p['size']):>10}  {p['files']:>4} files  {rng}")

    if report["steam"]:
        print("\nRECENTLY PLAYED (Steam LastPlayed):")
        for g in report["recent_games"][:20]:
            print(f"  {g['last_played']}  {g['name']}  (appid {g['appid']})")

    if report["pso"]:
        print("\nPER-GAME PSO/SHADER FOLDERS:")
        for p in report["pso"]:
            print(f"  {human(p['size']):>10}  {p['path']}")

    if report["attribution"]:
        print("\nATTRIBUTION (date clusters >= 500 MB, matched to games +-1 day):")
        for d, size, cnt, names in report["attribution"]:
            nm = ", ".join(names) if names else "(no recent game)"
            print(f"  {d}  {human(size):>10}  {cnt:>4} files  ->  {nm}")

    print("\nNote: this report is read-only; nothing was deleted.")


if __name__ == "__main__":
    main()
