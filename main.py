import os
import sys
import csv
import shlex
import uuid
import sqlite3
import shutil
import subprocess
import re
import difflib
import time
import hashlib
import urllib.request
import urllib.error
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QSettings, QObject, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QFont, QPixmap, QIcon, QColor, QPalette, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QFileDialog,
    QMessageBox, QDialog, QFormLayout, QDialogButtonBox, QTextEdit,
    QScrollArea, QFrame, QMenu, QButtonGroup, QSizePolicy, QSpacerItem, QColorDialog,
    QTabWidget, QInputDialog, QScrollArea, QListWidget, QListWidgetItem, QProgressBar,
    QGraphicsDropShadowEffect
)


from i18n import _tr, set_language
from ai_assistant import AssistantDialog


def _normalize_search_text(value):
    """Normalize names/paths for tolerant search while preserving Chinese characters."""
    value = str(value or "").casefold()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


def _fuzzy_search_score(query, *fields):
    """Fast relevance score for names, tags and paths; avoid expensive full-path diffs."""
    q = _normalize_search_text(query)
    if not q:
        return 1.0
    q_len = len(q)
    best = 0.0
    q_chars = set(q) if q_len >= 2 else None
    # Split once per field and only run edit-distance matching against plausible tokens.
    for field in fields:
        raw = str(field or "")
        if not raw:
            continue
        candidate = _normalize_search_text(raw)
        if not candidate:
            continue
        if q == candidate:
            return 1.0
        if q in candidate:
            best = max(best, 0.97 if len(candidate) <= q_len + 3 else 0.94)
            continue

        pieces = re.split(r"[\s\-_.\\/\[\](){}:,;]+", raw.casefold())
        for raw_piece in pieces:
            piece = _normalize_search_text(raw_piece)
            if not piece:
                continue
            if q == piece:
                return 1.0
            if q in piece:
                best = max(best, 0.94)
                continue
            # Very different lengths are almost never useful fuzzy matches; skip them.
            if q_len < 3 or abs(len(piece) - q_len) > max(2, q_len // 3):
                continue
            # Comparing short tokens is much cheaper than comparing an entire path.
            ratio = difflib.SequenceMatcher(None, q, piece, autojunk=True).quick_ratio()
            if ratio >= 0.55:
                ratio = difflib.SequenceMatcher(None, q, piece, autojunk=True).ratio()
                best = max(best, ratio * 0.91)

        # Character coverage helps Chinese / reordered queries, without a full-string diff.
        if q_chars is not None:
            coverage = len(q_chars.intersection(set(candidate))) / q_len
            best = max(best, coverage * 0.76)
        if best >= 0.97:
            return best

    # One-character searches are too ambiguous for typo matching.
    threshold = 0.50 if q_len >= 4 else 0.53 if q_len == 3 else 0.48 if q_len == 2 else 0.99
    return best if best >= threshold else 0.0


def _to_colorref(hex_color):
    """Convert #RRGGBB to the COLORREF layout expected by the Windows DWM API."""
    color = QColor(hex_color)
    if not color.isValid():
        color = QColor("#101218")
    return color.red() | (color.green() << 8) | (color.blue() << 16)


def apply_native_titlebar_theme(widget):
    """Match the native Windows title bar and border to GameShelf's active theme.

    This is deliberately best-effort: older Windows builds and non-Windows systems
    may not support all DWM attributes, so a failure must never stop the UI.
    """
    if sys.platform != "win32":
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        import ctypes
        hwnd_value = int(widget.winId())
        if not hwnd_value:
            return
        hwnd = ctypes.c_void_p(hwnd_value)
        dwmapi = ctypes.WinDLL("dwmapi")
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        set_attribute.restype = ctypes.c_long

        dark = bool(app.property("gameshelf_dark_mode"))
        is_dialog = bool(widget.inherits("QDialog"))
        caption_key = "gameshelf_dialog_caption_color" if is_dialog else "gameshelf_caption_color"
        caption = app.property(caption_key) or ("#191e29" if dark and is_dialog else "#101218" if dark else "#f5f7fb")
        border = app.property("gameshelf_border_color") or ("#2d3444" if dark else "#dce3ed")
        title_text = app.property("gameshelf_title_text_color") or ("#f1f3fa" if dark else "#20283a")

        def set_dword(attribute, value):
            data = ctypes.c_uint(int(value))
            return set_attribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))

        # Windows 11 uses attribute 20; 19 is the compatibility value on older builds.
        result = set_dword(20, 1 if dark else 0)
        if result != 0:
            set_dword(19, 1 if dark else 0)
        # Windows 11 custom caption/border colors. Unsupported values are harmlessly ignored.
        set_dword(34, _to_colorref(border))
        set_dword(35, _to_colorref(caption))
        set_dword(36, _to_colorref(title_text))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33; DWMWCP_ROUND = 2.
        # This rounds the actual native window frame on supported Windows 11 builds.
        set_dword(33, 2)
    except Exception:
        return


class NativeTitleBarThemeFilter(QObject):
    """Applies the active native title-bar theme to main windows and dialogs."""
    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Type.Show and isinstance(watched, QWidget) and watched.isWindow():
                QTimer.singleShot(0, lambda target=watched: apply_native_titlebar_theme(target))
        except (RuntimeError, TypeError):
            pass
        return False

APP_NAME = "Tutler"
APP_VERSION = "0.1.0"
# Keep the legacy data folder so existing GameShelf installations retain their database/settings.
APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GameShelf"
APP_ROOT = Path(__file__).resolve().parent
LOGO_PNG_PATH = APP_ROOT / "tutler-logo.png"
LOGO_ICO_PATH = APP_ROOT / "tutler.ico"
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / "gameshelf.db"
COVER_DIR = APP_DIR / "covers"
COVER_DIR.mkdir(parents=True, exist_ok=True)

try:
    import psutil
except ImportError:
    psutil = None

# 常见游戏类型缩写；保留 OTHER 作为默认分类。
CATEGORIES = ["ACT", "AVG", "RPG", "ARPG", "JRPG", "MMORPG", "FPS", "TPS", "RTS", "SLG", "SIM", "RAC", "SPG", "PUZ", "MUG", "MOBA", "ROGUE", "IND", "OTHER"]
LEGACY_CATEGORY_MAP = {
    "动作": "ACT", "冒险": "AVG", "角色扮演": "RPG", "射击": "FPS",
    "策略": "SLG", "模拟": "SIM", "竞速": "RAC", "体育": "SPG",
    "解谜": "PUZ", "独立游戏": "IND", "其他": "OTHER"
}
VIDEO_DEFAULT_CATEGORIES = []  # 视频库默认不预置任何分类
IMAGE_DEFAULT_CATEGORIES = []  # 图片库默认不预置任何分类
IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".webm", ".mpeg", ".mpg", ".ts", ".m2ts", ".3gp", ".flv", ".vob", ".ogv", ".mts"}


@contextmanager
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                exe_path TEXT NOT NULL UNIQUE,
                launch_args TEXT DEFAULT '',
                category TEXT DEFAULT '其他',
                tags TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                cover_path TEXT DEFAULT '',
                favorite INTEGER DEFAULT 0,
                play_count INTEGER DEFAULT 0,
                last_played TEXT DEFAULT '',
                playtime_seconds INTEGER DEFAULT 0,
                steam_appid TEXT DEFAULT '',
                install_dir TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                launched_at TEXT NOT NULL,
                FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
            )
        """)
        # 兼容旧版数据库：如果列不存在则追加，不会删除旧数据。
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
        migrations = {
            "launch_args": "TEXT DEFAULT ''",
            "category": "TEXT DEFAULT '其他'",
            "tags": "TEXT DEFAULT ''",
            "notes": "TEXT DEFAULT ''",
            "cover_path": "TEXT DEFAULT ''",
            "favorite": "INTEGER DEFAULT 0",
            "play_count": "INTEGER DEFAULT 0",
            "last_played": "TEXT DEFAULT ''",
            "playtime_seconds": "INTEGER DEFAULT 0",
            "steam_appid": "TEXT DEFAULT ''",
            "install_dir": "TEXT DEFAULT ''",
            "created_at": "TEXT DEFAULT ''",
        }
        for col, declaration in migrations.items():
            if col not in columns:
                conn.execute(f"ALTER TABLE games ADD COLUMN {col} {declaration}")
        # 将旧版中文分类映射到统一的类型缩写，游戏记录不会丢失。
        for old_name, new_name in LEGACY_CATEGORY_MAP.items():
            conn.execute("UPDATE games SET category=? WHERE category=?", (new_name, old_name))


def normalized_path(path):
    return os.path.normcase(os.path.abspath(os.path.expandvars(path.strip().strip('"'))))


def store_cover(source):
    """把封面复制到应用自己的数据目录，避免原图片被移动后失效。"""
    if not source:
        return ""
    source_path = Path(source)
    if not source_path.is_file():
        return ""
    suffix = source_path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return ""
    target = COVER_DIR / f"{uuid.uuid4().hex}{suffix}"
    shutil.copy2(source_path, target)
    return str(target)


def _is_auxiliary_exe(filename):
    """过滤崩溃处理器、卸载器、运行库安装器等非游戏主程序。"""
    name = Path(filename).name.casefold()
    stem = Path(name).stem
    exact_names = {
        "unitycrashhandler.exe", "unitycrashhandler32.exe", "unitycrashhandler64.exe",
        "crashreportclient.exe", "crashreporter.exe", "crashpad_handler.exe",
        "werfault.exe", "werfaultsecure.exe", "unins000.exe", "uninstall.exe",
        "uninstaller.exe", "unins.exe", "setup.exe", "dxsetup.exe",
        "vc_redist.x64.exe", "vc_redist.x86.exe", "vc_redist.arm64.exe",
        "vcredist_x64.exe", "vcredist_x86.exe", "vcredist.exe",
        "dotnetfx.exe", "ndp48-x86-x64-allos-enu.exe", "eac_launcher.exe",
        "battleye_launcher.exe", "easyanticheat_setup.exe", "reporter.exe",
    }
    if name in exact_names:
        return True
    # 这些关键词只用于明确的辅助程序命名，避免误伤名为 Crash/Launcher 的正式游戏。
    patterns = (
        r"^unitycrashhandler(?:32|64)?$", r"^crashreportclient(?:-.*)?$",
        r"^crashpad_handler(?:\.exe)?$", r"^unins\d*$", r"^uninstall(?:er)?$",
        r"^(?:vc_redist|vcredist)(?:[._-].*)?$", r"^dxsetup$",
        r"^easyanticheat(?:_setup)?$", r"^battleye(?:_launcher)?$",
    )
    return any(re.match(pattern, stem, flags=re.IGNORECASE) for pattern in patterns)


def find_exe_files(root):
    """递归发现可能的游戏 EXE，同时跳过常见安装器和辅助组件目录。"""
    ignored_dirs = {
        "redist", "redistributable", "__pycache__", ".git", "support",
        "directx", "easyanticheat", "battleye", "$recycle.bin",
        "system volume information", "installer", "installers", "_commonredist",
        "crashreporter", "crashreports", "logs", "temp", "tmp",
    }
    for current, dirs, files in os.walk(root, onerror=lambda _e: None):
        # 目录过滤大小写不敏感；不整体排除 Engine/Binaries，避免漏掉 Unreal 游戏主程序。
        dirs[:] = [d for d in dirs if d.casefold() not in ignored_dirs]
        for filename in files:
            if not filename.casefold().endswith(".exe") or _is_auxiliary_exe(filename):
                continue
            full_path = os.path.join(current, filename)
            try:
                if os.path.getsize(full_path) > 0:
                    yield full_path
            except OSError:
                continue


def steam_roots(custom_path=""):
    """Discover Steam installation roots and libraries, including a user-configured path."""
    roots = set()
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
        Path.home() / "AppData/Local/Programs/Steam",
        Path("D:/Steam"), Path("D:/Games/Steam"), Path("E:/Steam"), Path("E:/Games/Steam"),
    ]
    if custom_path:
        custom = Path(os.path.expandvars(custom_path.strip().strip('"')))
        if custom.is_file():
            custom = custom.parent
        if custom.name.lower() == "steamapps":
            custom = custom.parent
        if custom.is_dir():
            candidates.insert(0, custom)
    # Registry entries are optional; registry access can fail on non-Windows systems.
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for key_name in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _ = winreg.QueryValueEx(key, "SteamPath")
                        candidates.append(Path(value))
                except OSError:
                    pass
    except Exception:
        pass
    for candidate in candidates:
        if candidate.is_dir():
            roots.add(candidate.resolve())
    libraries = set(roots)
    for root in list(roots):
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if not vdf.exists():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            # Handles both modern "path" entries and older numeric entries.
            for raw in re.findall(r'"path"\s*"([^"]+)"', text):
                path = Path(raw.replace("\\\\", "\\"))
                if path.is_dir(): libraries.add(path)
            for raw in re.findall(r'"\d+"\s*"([A-Za-z]:\\\\[^"\r\n]+)"', text):
                path = Path(raw.replace("\\\\", "\\"))
                if path.is_dir(): libraries.add(path)
        except OSError:
            pass
    return sorted(libraries, key=lambda x: str(x).lower())


def steam_manifest_games(custom_path=""):
    """Return installed Steam games from appmanifest files."""
    results = []
    seen = set()
    for library in steam_roots(custom_path):
        apps_dir = library / "steamapps"
        if not apps_dir.is_dir():
            continue
        for manifest in apps_dir.glob("appmanifest_*.acf"):
            try:
                raw = manifest.read_text(encoding="utf-8", errors="ignore")
                def field(key, default=""):
                    m = re.search(r'"' + re.escape(key) + r'"\s*"([^"]*)"', raw)
                    return m.group(1) if m else default
                appid, name = field("appid"), field("name")
                installdir = field("installdir")
                if not appid or not name or appid in seen:
                    continue
                install_dir = apps_dir / "common" / installdir
                if not install_dir.is_dir():
                    continue
                seen.add(appid)
                results.append({"appid": appid, "name": name, "install_dir": str(install_dir),
                                "library": str(library), "manifest": str(manifest)})
            except OSError:
                continue
    return results


def guess_game_exe(install_dir, game_name):
    """按游戏名、目录位置和文件体积排序，尽量选出真正的游戏主程序。"""
    root = Path(install_dir)
    candidates = list(find_exe_files(str(root)))
    if not candidates:
        return ""
    game_key = re.sub(r"[^a-z0-9]", "", game_name.casefold())
    scored = []
    soft_penalties = ("launcher", "bootstrap", "updater", "update", "repair", "helper", "service")
    for path in candidates:
        p = Path(path)
        key = re.sub(r"[^a-z0-9]", "", p.stem.casefold())
        score = 0
        if key and game_key and key == game_key:
            score += 160
        elif key and game_key and (key in game_key or game_key in key):
            score += 90
        elif key and game_key and any(part and part in key for part in re.findall(r"[a-z0-9]+", game_name.casefold()) if len(part) >= 4):
            score += 25
        try:
            relative_parts = [part.casefold() for part in p.relative_to(root).parts[:-1]]
        except ValueError:
            relative_parts = []
        if not relative_parts:
            score += 35
        elif any(part in {"binaries", "win64", "win32", "shipping"} for part in relative_parts):
            score += 12
        if any(word in p.stem.casefold() for word in soft_penalties):
            score -= 35
        try:
            score += min(p.stat().st_size // (1024 * 1024), 40)
        except OSError:
            pass
        scored.append((score, -len(str(p)), str(p).casefold(), str(p)))
    scored.sort(reverse=True)
    return scored[0][3]


def download_steam_cover(appid):
    """Fetch the Steam store header image; returns a local cached path or empty string."""
    if not appid:
        return ""
    target = COVER_DIR / f"steam_{appid}.jpg"
    if target.exists() and target.stat().st_size > 2048:
        return str(target)
    urls = [
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Tutler/0.1.0"})
            with urllib.request.urlopen(req, timeout=8) as response:
                data = response.read(8 * 1024 * 1024)
            if len(data) > 2048 and data[:2] == b'\xff\xd8':
                target.write_bytes(data)
                return str(target)
        except Exception:
            continue
    return ""


def _log_icon_debug(message):
    """把图标提取的诊断信息写入日志文件，便于定位失败原因。"""
    try:
        log_path = APP_DIR / "icon_extract_debug.log"
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {str(message).strip()}\n")
    except Exception:
        pass


def extract_exe_icon_as_cover(exe_path):
    """把 EXE 内嵌图标提取为本地 PNG 封面（仅 Windows；失败返回空字符串）。

    按可靠性依次尝试三种方式：
    1. Qt 的 QFileIconProvider（走系统图标提取，通常最稳定）；
    2. SHGetFileInfo 取大图标；
    3. ExtractIconEx 取大图标。
    每一步失败都会记录到 APP_DIR 下的 icon_extract_debug.log。
    """
    if sys.platform != "win32":
        return ""
    if not exe_path or exe_path.lower().startswith("steam://"):
        return ""
    target = Path(exe_path)
    if not target.is_file():
        _log_icon_debug(f"文件不存在，跳过：{exe_path}")
        return ""

    try:
        from PySide6.QtCore import QFileInfo
        from PySide6.QtGui import QPixmap, QImage, QPainter
        from PySide6.QtWidgets import QFileIconProvider
    except Exception as exc:
        _log_icon_debug(f"Qt 组件导入失败：{exc}")
        return ""

    source = None

    # 方式 1：QFileIconProvider（系统会为 EXE 解析出内嵌图标）
    try:
        icon = QFileIconProvider().icon(QFileInfo(str(target)))
        sizes = icon.availableSizes()
        pm = None
        if sizes:
            biggest = max(sizes, key=lambda s: s.width() * s.height())
            pm = icon.pixmap(biggest)
        else:
            pm = icon.pixmap(48, 48)
        if pm is not None and not pm.isNull() and pm.width() >= 16:
            source = pm
        else:
            _log_icon_debug(f"QFileIconProvider 未获得有效图标：{exe_path}（sizes={[(s.width(), s.height()) for s in sizes]}）")
    except Exception as exc:
        _log_icon_debug(f"QFileIconProvider 失败：{exe_path} -> {exc}")

    # 方式 2：SHGetFileInfo 取大图标
    if source is None:
        try:
            import ctypes
            from ctypes import wintypes

            class SHFILEINFO(ctypes.Structure):
                _fields_ = [
                    ("hIcon", wintypes.HICON),
                    ("iIcon", ctypes.c_int),
                    ("dwAttributes", wintypes.DWORD),
                    ("szDisplayName", wintypes.WCHAR * 260),
                    ("szTypeName", wintypes.WCHAR * 80),
                ]

            sh_get_file_info = ctypes.windll.shell32.SHGetFileInfoW
            sh_get_file_info.restype = ctypes.c_size_t
            sh_get_file_info.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.POINTER(SHFILEINFO), wintypes.UINT, wintypes.UINT,
            ]
            sfi = SHFILEINFO()
            # SHGFI_ICON(0x100)，大图标标志 SHGFI_LARGEICON 为 0
            res = sh_get_file_info(str(target), 0, ctypes.byref(sfi), ctypes.sizeof(sfi), 0x100)
            if res and sfi.hIcon:
                pm = QPixmap.fromWinHICON(int(sfi.hIcon))
                ctypes.windll.user32.DestroyIcon(sfi.hIcon)
                if pm is not None and not pm.isNull() and pm.width() >= 16:
                    source = pm
                else:
                    _log_icon_debug(f"SHGetFileInfo 句柄转 QPixmap 失败：{exe_path}")
            else:
                _log_icon_debug(f"SHGetFileInfo 返回空句柄：{exe_path}")
        except Exception as exc:
            _log_icon_debug(f"SHGetFileInfo 失败：{exe_path} -> {exc}")

    # 方式 3：ExtractIconEx 取大图标
    if source is None:
        try:
            import ctypes
            from ctypes import wintypes

            extract_icon_ex = ctypes.windll.shell32.ExtractIconExW
            large_icon = wintypes.HICON()
            small_icon = wintypes.HICON()
            count = extract_icon_ex(
                str(target), 0,
                ctypes.byref(large_icon), ctypes.byref(small_icon), 1
            )
            handle = large_icon or small_icon
            if count and handle:
                pm = QPixmap.fromWinHICON(int(handle))
                ctypes.windll.user32.DestroyIcon(handle)
                if pm is not None and not pm.isNull() and pm.width() >= 16:
                    source = pm
                else:
                    _log_icon_debug(f"ExtractIconEx 句柄转 QPixmap 失败：{exe_path}")
            else:
                _log_icon_debug(f"ExtractIconEx 未提取到图标：{exe_path}")
            if small_icon and small_icon != handle:
                ctypes.windll.user32.DestroyIcon(small_icon)
        except Exception as exc:
            _log_icon_debug(f"ExtractIconEx 失败：{exe_path} -> {exc}")

    if source is None or source.isNull():
        _log_icon_debug(f"所有方式均失败，放弃：{exe_path}")
        return ""

    try:
        # 合成到 256x256 透明画布上居中显示，避免小图标在卡片里被强行拉伸变形
        size = 256
        canvas = QImage(size, size, QImage.Format.Format_ARGB32)
        canvas.fill(0)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scaled = source.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()

        out = COVER_DIR / f"exe_icon_{uuid.uuid4().hex}.png"
        if canvas.save(str(out), "PNG"):
            return str(out)
        _log_icon_debug(f"PNG 保存失败：{out}")
        return ""
    except Exception as exc:
        _log_icon_debug(f"合成封面失败：{exe_path} -> {exc}")
        return ""


class SteamScanWorker(QThread):
    progress = Signal(str)
    found = Signal(list)
    failed = Signal(str)

    def __init__(self, download_covers=True, custom_path="", parent=None):
        super().__init__(parent)
        self.download_covers = download_covers
        self.custom_path = custom_path

    def run(self):
        try:
            games = steam_manifest_games(self.custom_path)
            for i, game in enumerate(games, 1):
                self.progress.emit(f"正在识别 Steam 游戏…{i}/{len(games)}：{game['name']}")
                game["exe_path"] = guess_game_exe(game["install_dir"], game["name"])
                game["cover_path"] = download_steam_cover(game["appid"]) if self.download_covers else ""
            self.found.emit(games)
        except Exception as exc:
            self.failed.emit(str(exc))


class ScanWorker(QThread):
    progress = Signal(str)
    found = Signal(list)
    failed = Signal(str)

    def __init__(self, root):
        super().__init__()
        self.root = root

    def run(self):
        try:
            found = []
            for path in find_exe_files(self.root):
                found.append(path)
                if len(found) % 100 == 0:
                    self.progress.emit(f"正在扫描…已发现 {len(found)} 个 EXE")
            self.found.emit(found)
        except Exception as exc:
            self.failed.emit(str(exc))


class VideoScanWorker(QThread):
    progress = Signal(str)
    found = Signal(list)
    failed = Signal(str)

    def __init__(self, roots, parent=None):
        super().__init__(parent)
        self.roots = list(roots)

    def run(self):
        try:
            videos = set()
            for root in self.roots:
                if not os.path.isdir(root):
                    continue
                for current, dirs, files in os.walk(root, onerror=lambda _e: None):
                    # Ignore common cache and recycle folders to avoid irrelevant files.
                    dirs[:] = [d for d in dirs if d.lower() not in {"$recycle.bin", "system volume information", "windows", "programdata"}]
                    for filename in files:
                        if Path(filename).suffix.lower() in VIDEO_EXTENSIONS:
                            full_path = os.path.abspath(os.path.join(current, filename))
                            videos.add(full_path)
                            if len(videos) % 100 == 0:
                                self.progress.emit(f"正在扫描视频…已发现 {len(videos)} 个文件")
            self.found.emit(sorted(videos, key=lambda x: os.path.basename(x).casefold()))
        except Exception as exc:
            self.failed.emit(str(exc))


def video_thumbnail_path(video_path):
    """Stable cache path based on file path and modification time."""
    try:
        stat = os.stat(video_path)
        signature = f"{os.path.abspath(video_path)}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        signature = os.path.abspath(video_path)
    key = hashlib.sha1(signature.encode("utf-8", errors="ignore")).hexdigest()
    thumb_dir = APP_DIR / "video_thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f"{key}.jpg"


class VideoThumbnailWorker(QThread):
    """Generate video preview frames off the UI thread when ffmpeg is available."""
    completed = Signal(int)

    def __init__(self, video_paths, parent=None):
        super().__init__(parent)
        self.video_paths = list(video_paths)
        self.generated_count = 0

    def run(self):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return
        generated = 0
        for video_path in self.video_paths:
            if not os.path.isfile(video_path):
                continue
            target = video_thumbnail_path(video_path)
            if target.is_file() and target.stat().st_size > 0:
                continue
            # Seek near the beginning; retry at the first frame for very short clips.
            commands = [
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "00:00:01", "-i", video_path, "-frames:v", "1", "-vf", "scale=480:270:force_original_aspect_ratio=decrease", "-q:v", "4", str(target)],
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", video_path, "-frames:v", "1", "-vf", "scale=480:270:force_original_aspect_ratio=decrease", "-q:v", "4", str(target)],
            ]
            for command in commands:
                try:
                    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    if result.returncode == 0 and target.is_file() and target.stat().st_size > 0:
                        generated += 1
                        break
                except (OSError, subprocess.TimeoutExpired):
                    continue
            else:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
        self.generated_count = generated


class ImageScanWorker(QThread):
    progress = Signal(str)
    found = Signal(list)
    failed = Signal(str)

    def __init__(self, roots, parent=None):
        super().__init__(parent)
        self.roots = list(roots)

    def run(self):
        try:
            images = set()
            ignored = {"$recycle.bin", "system volume information", "windows", "programdata", "__pycache__", ".git"}
            for root in self.roots:
                if not os.path.isdir(root):
                    continue
                for current, dirs, files in os.walk(root, onerror=lambda _e: None):
                    dirs[:] = [d for d in dirs if d.lower() not in ignored]
                    for filename in files:
                        if Path(filename).suffix.lower() in IMAGE_EXTENSIONS:
                            images.add(os.path.abspath(os.path.join(current, filename)))
                            if len(images) and len(images) % 100 == 0:
                                self.progress.emit(f"正在扫描图片…已发现 {len(images)} 个文件")
            self.found.emit(sorted(images, key=lambda x: os.path.basename(x).casefold()))
        except Exception as exc:
            self.failed.emit(str(exc))


class VideoCard(QFrame):
    play_requested = Signal(str)
    category_changed = Signal(str, str)
    remove_requested = Signal(str)

    def __init__(self, video_path, categories=None, current_category="", parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.setObjectName("GameCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(250)
        self.setMaximumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 14, 13, 13)
        layout.setSpacing(9)

        preview = QLabel()
        preview.setObjectName("VideoPreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(150)
        preview.setMaximumHeight(150)
        preview.setScaledContents(False)
        thumb_path = video_thumbnail_path(video_path)
        pixmap = QPixmap(str(thumb_path)) if thumb_path.is_file() else QPixmap()
        if not pixmap.isNull():
            preview.setPixmap(pixmap.scaled(380, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            preview.setText("▶\n视频预览生成中" if shutil.which("ffmpeg") else "▶\n视频封面需要 FFmpeg")
        preview.setToolTip("视频预览帧" if not pixmap.isNull() else "安装 FFmpeg 并重新打开视频库可生成视频封面")
        layout.addWidget(preview)

        name = QLabel(Path(video_path).stem)
        name.setObjectName("CardTitle")
        name.setWordWrap(True)
        name.setMinimumHeight(38)
        name.setToolTip(video_path)
        layout.addWidget(name)

        try:
            size = os.path.getsize(video_path)
            if size >= 1024 ** 3:
                size_text = f"{size / 1024 ** 3:.2f} GB"
            else:
                size_text = f"{size / 1024 ** 2:.0f} MB"
        except OSError:
            size_text = "大小未知"
        info = QLabel(f"{Path(video_path).suffix.upper().lstrip('.')}  ·  {size_text}")
        info.setObjectName("Muted")
        layout.addWidget(info)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("分类"))
        self.category_box = QComboBox()
        self.category_box.addItem("（无分类）", "")
        for category in (categories or []):
            self.category_box.addItem(category, category)
        idx = self.category_box.findData(current_category or "")
        self.category_box.setCurrentIndex(max(0, idx))
        self.category_box.currentIndexChanged.connect(lambda _index: self.category_changed.emit(video_path, self.category_box.currentData() or ""))
        category_row.addWidget(self.category_box, 1)
        layout.addLayout(category_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        play_btn = QPushButton("▶  播放")
        play_btn.setObjectName("PrimaryButton")
        play_btn.clicked.connect(lambda: self.play_requested.emit(video_path))
        remove_btn = QPushButton("移除")
        remove_btn.setObjectName("SecondaryButton")
        remove_btn.setToolTip("仅从 Tutler 视频库中移除，不会删除硬盘上的视频文件")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(video_path))
        action_row.addWidget(play_btn, 1)
        action_row.addWidget(remove_btn)
        layout.addLayout(action_row)


class ImageCard(QFrame):
    open_requested = Signal(str)
    category_changed = Signal(str, str)
    remove_requested = Signal(str)

    def __init__(self, image_path, categories=None, current_category="", parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setObjectName("GameCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(250)
        self.setMaximumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 14, 13, 13)
        layout.setSpacing(9)

        preview = QLabel()
        preview.setObjectName("ImagePreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(150)
        preview.setMaximumHeight(150)
        preview.setScaledContents(False)
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            preview.setPixmap(pixmap.scaled(340, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            preview.setText("图片预览不可用")
        layout.addWidget(preview)

        name = QLabel(Path(image_path).name)
        name.setObjectName("CardTitle")
        name.setWordWrap(True)
        name.setMinimumHeight(38)
        name.setToolTip(image_path)
        layout.addWidget(name)

        try:
            size = os.path.getsize(image_path)
            size_text = f"{size / 1024 ** 2:.2f} MB" if size >= 1024 ** 2 else f"{size / 1024:.0f} KB"
        except OSError:
            size_text = "大小未知"
        info = QLabel(f"{Path(image_path).suffix.upper().lstrip('.')}  ·  {size_text}")
        info.setObjectName("Muted")
        layout.addWidget(info)

        category_row = QHBoxLayout()
        category_row.addWidget(QLabel("分类"))
        self.category_box = QComboBox()
        self.category_box.addItem("（无分类）", "")
        for category in (categories or []):
            self.category_box.addItem(category, category)
        idx = self.category_box.findData(current_category or "")
        self.category_box.setCurrentIndex(max(0, idx))
        self.category_box.currentIndexChanged.connect(lambda _index: self.category_changed.emit(image_path, self.category_box.currentData() or ""))
        category_row.addWidget(self.category_box, 1)
        layout.addLayout(category_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        open_btn = QPushButton("打开图片")
        open_btn.setObjectName("PrimaryButton")
        open_btn.clicked.connect(lambda: self.open_requested.emit(image_path))
        remove_btn = QPushButton("移除")
        remove_btn.setObjectName("SecondaryButton")
        remove_btn.setToolTip("仅从 Tutler 图片库中移除，不会删除硬盘上的图片文件")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(image_path))
        action_row.addWidget(open_btn, 1)
        action_row.addWidget(remove_btn)
        layout.addLayout(action_row)


class GameDialog(QDialog):
    def __init__(self, parent=None, game=None, suggested_path="", categories=None):
        super().__init__(parent)
        self.setWindowTitle("编辑游戏" if game else "添加游戏")
        self.setMinimumWidth(610)
        self.game = game
        self.cover_path = (game["cover_path"] or "") if game else ""
        self.steam_appid = (game["steam_appid"] or "") if game and "steam_appid" in game.keys() else ""
        self.install_dir = (game["install_dir"] or "") if game and "install_dir" in game.keys() else ""

        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.name_edit = QLineEdit()
        self.path_edit = QLineEdit()
        self.args_edit = QLineEdit()
        self.category_box = QComboBox()
        self.category_box.addItems(categories or CATEGORIES)
        self.tags_edit = QLineEdit()
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(75)
        self.path_edit.setPlaceholderText(r"例如：D:\Games\MyGame\Game.exe")
        self.args_edit.setPlaceholderText('可选，例如：-windowed -language "zh-CN"')
        self.tags_edit.setPlaceholderText("动作, 单机, 手柄")

        path_row = QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_btn = QPushButton("浏览…")
        path_btn.clicked.connect(self.browse_exe)
        path_row.addWidget(path_btn)

        cover_row = QHBoxLayout()
        self.cover_preview = QLabel()
        self.cover_preview.setFixedSize(124, 76)
        self.cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_preview.setObjectName("CoverPreview")
        self.cover_label = QLabel("尚未选择封面")
        self.cover_label.setWordWrap(True)
        cover_row.addWidget(self.cover_preview)
        cover_row.addWidget(self.cover_label, 1)
        cover_btn = QPushButton("选择图片…")
        cover_btn.clicked.connect(self.browse_cover)
        cover_row.addWidget(cover_btn)
        clear_cover_btn = QPushButton("清除")
        clear_cover_btn.clicked.connect(self.clear_cover)
        cover_row.addWidget(clear_cover_btn)

        form.addRow("游戏名称", self.name_edit)
        form.addRow("游戏 EXE", path_row)
        form.addRow("启动参数", self.args_edit)
        form.addRow("游戏分类", self.category_box)
        form.addRow("标签", self.tags_edit)
        form.addRow("游戏封面", cover_row)
        form.addRow("备注", self.notes_edit)
        outer.addLayout(form)

        hint = QLabel("封面会复制到 Tutler 的本地数据目录。移除游戏记录不会删除游戏本体。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        if game:
            self.name_edit.setText(game["name"] or "")
            self.path_edit.setText(game["exe_path"] or "")
            self.args_edit.setText(game["launch_args"] or "")
            idx = self.category_box.findText(game["category"] or "其他")
            self.category_box.setCurrentIndex(max(0, idx))
            self.tags_edit.setText(game["tags"] or "")
            self.notes_edit.setPlainText(game["notes"] or "")
        elif suggested_path:
            self.path_edit.setText(suggested_path)
            self.name_edit.setText(Path(suggested_path).stem)
        self.update_cover_preview()

    def browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏可执行文件", "", "Windows 程序 (*.exe);;所有文件 (*.*)"
        )
        if path:
            self.path_edit.setText(path)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).stem)
            # 选完 EXE 立即提取内嵌图标作为封面预览（用户仍可手动更换或清除）
            if not self.cover_path:
                extracted = extract_exe_icon_as_cover(path)
                if extracted:
                    self.cover_path = extracted
                    self.update_cover_preview()

    def browse_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择游戏封面", "", IMAGE_FILTER)
        if path:
            try:
                self.cover_path = store_cover(path)
                if not self.cover_path:
                    raise ValueError("无法读取或复制所选图片。")
                self.update_cover_preview()
            except Exception as exc:
                QMessageBox.warning(self, "封面设置失败", str(exc))

    def clear_cover(self):
        self.cover_path = ""
        self.update_cover_preview()

    def update_cover_preview(self):
        self.cover_preview.clear()
        if self.cover_path and os.path.isfile(self.cover_path):
            pixmap = QPixmap(self.cover_path)
            if not pixmap.isNull():
                self.cover_preview.setPixmap(
                    pixmap.scaled(
                        self.cover_preview.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
                self.cover_label.setText(Path(self.cover_path).name)
                return
        self.cover_preview.setText("NO COVER")
        self.cover_label.setText("尚未选择封面")

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip().strip('"')
        if not name:
            QMessageBox.warning(self, "信息不完整", "请输入游戏名称。")
            return
        is_steam_uri = path.lower().startswith("steam://rungameid/")
        if not path or (not is_steam_uri and not os.path.isfile(path)):
            QMessageBox.warning(self, "路径无效", "请选择一个存在的 EXE 文件或有效的 Steam 游戏。")
            return
        if not is_steam_uri and not path.lower().endswith(".exe"):
            QMessageBox.warning(self, "文件类型不支持", "第一版仅支持 Windows .exe 文件。")
            return
        # 用户直接手输路径、未经过浏览按钮时，保存前再尝试提取一次图标
        if not self.cover_path and not is_steam_uri and os.path.isfile(path):
            extracted = extract_exe_icon_as_cover(path)
            if extracted:
                self.cover_path = extracted
        self.accept()

    def values(self):
        return {
            "name": self.name_edit.text().strip(),
            "exe_path": (self.path_edit.text().strip().strip('"') if self.path_edit.text().strip().lower().startswith("steam://rungameid/") else normalized_path(self.path_edit.text())),
            "launch_args": self.args_edit.text().strip(),
            "category": self.category_box.currentText(),
            "tags": self.tags_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "cover_path": self.cover_path,
            "steam_appid": self.steam_appid,
            "install_dir": self.install_dir,
        }


class GameCard(QFrame):
    launch_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    favorite_requested = Signal(int, bool)

    def __init__(self, game, parent=None):
        super().__init__(parent)
        self.game = game
        self.setObjectName("GameCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(250)
        self.setMaximumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(10)

        cover_box = QFrame()
        cover_box.setObjectName("CoverBox")
        cover_box.setFixedHeight(166)
        cover_layout = QVBoxLayout(cover_box)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover = QLabel()
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setObjectName("CoverImage")
        cover.setMinimumHeight(166)
        cover.setMaximumHeight(166)
        cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cover_path = game["cover_path"] or ""
        pix = QPixmap(cover_path) if cover_path and os.path.isfile(cover_path) else QPixmap()
        if not pix.isNull():
            cover.setPixmap(pix.scaled(
                QSize(420, 166), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            ))
            cover.setToolTip(game["name"])
        else:
            cover.setText("🎮\nNO COVER")
            cover.setObjectName("CoverPlaceholder")
        cover_layout.addWidget(cover)
        layout.addWidget(cover_box)

        title_row = QHBoxLayout()
        name = QLabel(game["name"])
        name.setObjectName("CardTitle")
        name.setWordWrap(True)
        name.setMinimumHeight(44)
        name.setToolTip(game["name"])
        title_row.addWidget(name, 1)
        fav_btn = QPushButton("★" if game["favorite"] else "☆")
        fav_btn.setObjectName("FavoriteButton")
        fav_btn.setFixedSize(34, 34)
        fav_btn.setToolTip("取消收藏" if game["favorite"] else "加入收藏")
        fav_btn.clicked.connect(
            lambda: self.favorite_requested.emit(game["id"], not bool(game["favorite"]))
        )
        title_row.addWidget(fav_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(title_row)

        category = QLabel(game["category"] or "其他")
        category.setObjectName("Muted")
        layout.addWidget(category)

        tags = (game["tags"] or "").strip()
        if tags:
            tags_label = QLabel(tags)
            tags_label.setObjectName("TagsLabel")
            tags_label.setWordWrap(True)
            layout.addWidget(tags_label)

        if game["last_played"]:
            last = QLabel("最近游玩  " + game["last_played"])
            last.setObjectName("Muted")
            layout.addWidget(last)

        button_row = QHBoxLayout()
        launch = QPushButton("▶  启动游戏")
        launch.setObjectName("PrimaryButton")
        launch.clicked.connect(lambda: self.launch_requested.emit(game["id"]))
        button_row.addWidget(launch, 2)
        more = QPushButton("编辑")
        more.clicked.connect(lambda: self.edit_requested.emit(game["id"]))
        button_row.addWidget(more, 1)
        remove = QPushButton("移除")
        remove.clicked.connect(lambda: self.delete_requested.emit(game["id"]))
        button_row.addWidget(remove, 1)
        layout.addLayout(button_row)


class WindowControlButton(QPushButton):
    """绘制像素尺寸统一的窗口控制图标，避免不同字体导致符号大小不一。"""
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName("WindowCloseButton" if kind == "close" else "WindowControlButton")
        self.setFixedSize(46, 46)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName({"minimize": "最小化", "maximize": "最大化", "restore": "还原", "close": "关闭"}[kind])
        self.setToolTip(self.accessibleName())

    def set_kind(self, kind):
        self.kind = kind
        self.setAccessibleName({"minimize": "最小化", "maximize": "最大化", "restore": "还原", "close": "关闭"}[kind])
        self.setToolTip(self.accessibleName())
        self.update()

    def paintEvent(self, event):
        # Paint the button background first; draw every glyph in a centered 12x12
        # coordinate system so its visual bounds are centered, not just its anchor.
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#ffffff") if self.kind == "close" and self.underMouse() else QColor(self.palette().color(QPalette.ColorRole.ButtonText))
        painter.setPen(QPen(color, 1.35, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Center a 12px icon canvas inside the full button rect, independent of
        # layout margins, font metrics, or the current device scale factor.
        painter.translate((self.width() - 12) / 2.0, (self.height() - 12) / 2.0)
        if self.kind == "minimize":
            painter.drawLine(1.5, 6.5, 10.5, 6.5)
        elif self.kind == "maximize":
            painter.drawRect(2.0, 2.0, 8.0, 8.0)
        elif self.kind == "restore":
            # Two overlapping windows; the overall visible bounds are centered.
            painter.drawLine(4.0, 1.5, 10.0, 1.5)
            painter.drawLine(10.0, 1.5, 10.0, 7.5)
            painter.drawLine(4.0, 1.5, 4.0, 3.0)
            painter.drawLine(2.0, 4.0, 8.0, 4.0)
            painter.drawLine(8.0, 4.0, 8.0, 10.0)
            painter.drawLine(2.0, 4.0, 2.0, 10.0)
            painter.drawLine(2.0, 10.0, 8.0, 10.0)
        elif self.kind == "close":
            painter.drawLine(3.0, 3.0, 9.0, 9.0)
            painter.drawLine(9.0, 3.0, 3.0, 9.0)
        painter.end()


class ModernTitleBar(QWidget):
    """轻量自绘标题栏：统一品牌区与窗口控制按钮。"""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName("ModernTitleBar")
        self.setFixedHeight(46)
        self._drag_offset = None
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 8, 0)
        row.setSpacing(10)

        mark = QLabel()
        mark.setObjectName("TitleBarLogo")
        mark.setFixedSize(25, 25)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if LOGO_PNG_PATH.exists():
            mark.setPixmap(QPixmap(str(LOGO_PNG_PATH)).scaled(
                25, 25, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            mark.setText("T")
        row.addWidget(mark)

        name = QLabel("Tutler")
        name.setObjectName("TitleBarName")
        row.addWidget(name)
        version = QLabel("GAME LIBRARY")
        version.setObjectName("TitleBarSub")
        row.addWidget(version)
        row.addStretch(1)

        self.min_button = WindowControlButton("minimize", self)
        self.min_button.clicked.connect(window.showMinimized)
        row.addWidget(self.min_button)

        self.max_button = WindowControlButton("maximize", self)
        self.max_button.clicked.connect(self.toggle_maximize)
        row.addWidget(self.max_button)

        self.close_button = WindowControlButton("close", self)
        self.close_button.clicked.connect(window.close)
        row.addWidget(self.close_button)

    def toggle_maximize(self):
        if self.window.isMaximized():
            self.window.showNormal()
            self.max_button.set_kind("maximize")
        else:
            self.window.showMaximized()
            self.max_button.set_kind("restore")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class GameShelfWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Tutler")
        if LOGO_ICO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_ICO_PATH)))
        self.resize(1440, 920)
        self.setMinimumSize(1080, 680)
        self.scan_worker = None
        self.steam_worker = None
        self._active_play = None
        self.playtime_timer = QTimer(self)
        self.playtime_timer.setInterval(5000)
        self.playtime_timer.timeout.connect(self._tick_playtime)
        self.playtime_timer.start()
        self.settings = QSettings("GameShelf", "GameShelf")
        # v3.7 migration requested by the user: clear all previous video/image categories
        # and assignments once, while preserving the indexed media files and scan roots.
        if not self.settings.value("media_categories_reset_v37", False, type=bool):
            for key, empty_value in (
                ("custom_video_categories", []), ("video_category_order", []), ("video_category_map", {}),
                ("custom_image_categories", []), ("image_category_order", []), ("image_category_map", {}),
            ):
                self.settings.setValue(key, empty_value)
            self.settings.setValue("media_categories_reset_v37", True)
            self.settings.sync()
        self.video_worker = None
        self.video_files = list(self.settings.value("video_files", [], type=list))
        self._toast_widget = None
        self._progress_toasts = {}
        self.accent_color = self.settings.value("theme_color", "#7867f5", type=str)
        self.theme_mode = self.settings.value("theme_mode", "system", type=str)
        if not QColor(self.accent_color).isValid():
            self.accent_color = "#7867f5"
        self.current_view = "all"
        self.current_category = ""
        self.current_video_category = ""
        self.custom_categories = self._load_custom_categories()
        self.custom_video_categories = self._load_custom_video_categories()
        self.custom_image_categories = self._load_custom_image_categories()
        raw_video_category_map = self.settings.value("video_category_map", {})
        if isinstance(raw_video_category_map, str):
            try:
                import json
                raw_video_category_map = json.loads(raw_video_category_map)
            except (ValueError, TypeError):
                raw_video_category_map = {}
        self.video_category_map = dict(raw_video_category_map) if isinstance(raw_video_category_map, dict) else {}
        raw_image_category_map = self.settings.value("image_category_map", {})
        if isinstance(raw_image_category_map, str):
            try:
                import json
                raw_image_category_map = json.loads(raw_image_category_map)
            except (ValueError, TypeError):
                raw_image_category_map = {}
        self.image_category_map = dict(raw_image_category_map) if isinstance(raw_image_category_map, dict) else {}
        # Previous versions had built-in video categories; those are no longer defaults.
        for path, category in list(self.video_category_map.items()):
            if category in {"未分类", "电影", "电视剧", "动画", "纪录片", "课程", "其他"} and category not in self.custom_video_categories:
                self.video_category_map[path] = ""
        self.image_files = list(self.settings.value("image_files", [], type=list))
        self.video_worker = None
        self.image_worker = None
        self.video_thumbnail_worker = None
        # When a directory is selected while viewing a custom media category,
        # newly discovered files under that directory are assigned to that category.
        self._pending_video_category_assignment = None
        self._pending_image_category_assignment = None
        self.current_image_category = ""
        self.category_nav_buttons = {}
        self.video_category_nav_buttons = {}
        self.image_category_nav_buttons = {}
        self.nav_buttons = []
        self._assistant_dialog = None
        self.assistant_button = None
        self._build_ui()
        self._create_ai_floating_button()
        # 应用启动时始终进入“全部游戏”，不自动展开或切换到某个分类。
        self.all_btn.setChecked(True)
        self.change_view("all")
        QTimer.singleShot(300, self._backfill_missing_covers)
        if self.settings.value("auto_scan_steam", False, type=bool):
            QTimer.singleShot(700, self.scan_steam_games)

    def _create_ai_floating_button(self):
        """创建始终浮在启动器内容之上的圆形 AI 入口。"""
        self.assistant_button = QPushButton("✦", self)
        self.assistant_button.setObjectName("AIFloatingButton")
        self.assistant_button.setFixedSize(62, 62)
        self.assistant_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.assistant_button.setToolTip("Tutler AI · 点击开始对话" if self.settings.value("language", "zh_CN", type=str) != "en_US" else "Tutler AI · Click to chat")
        self.assistant_button.setFont(QFont("Segoe UI Symbol", 22, QFont.Weight.Bold))
        self.assistant_button.clicked.connect(self.toggle_ai_assistant)
        self._style_ai_floating_button()
        self._position_ai_floating_button()
        self.assistant_button.show()
        self.assistant_button.raise_()

    def _style_ai_floating_button(self):
        button = getattr(self, "assistant_button", None)
        if button is None:
            return
        accent = QColor(getattr(self, "accent_color", "#7867f5"))
        if not accent.isValid():
            accent = QColor("#7867f5")
        accent_hover = accent.lighter(112).name()
        accent_border = accent.lighter(125).name()
        button.setStyleSheet(f"""
            QPushButton#AIFloatingButton {{
                color: #ffffff;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {accent.name()}, stop:1 {accent.darker(125).name()});
                border: 1px solid {accent_border};
                border-radius: 31px;
                padding: 0;
                font-family: "Segoe UI Symbol", "Microsoft YaHei UI", sans-serif;
                font-size: 25px;
                font-weight: 800;
            }}
            QPushButton#AIFloatingButton:hover {{
                background: {accent_hover}; border-color: {accent_hover};
            }}
            QPushButton#AIFloatingButton:pressed {{
                background: {accent.darker(115).name()};
            }}
        """)
        shadow = button.graphicsEffect()
        if not isinstance(shadow, QGraphicsDropShadowEffect):
            shadow = QGraphicsDropShadowEffect(button)
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 5)
            button.setGraphicsEffect(shadow)
        shadow_color = QColor(accent)
        shadow_color.setAlpha(135)
        shadow.setColor(shadow_color)

    def _position_ai_floating_button(self):
        button = getattr(self, "assistant_button", None)
        if button is None:
            return
        margin = 24
        button.move(max(12, self.width() - button.width() - margin),
                    max(60, self.height() - button.height() - margin))
        button.raise_()

    def toggle_ai_assistant(self):
        """Open/close the chat panel without blocking the launcher window."""
        if self._assistant_dialog is None:
            self._assistant_dialog = AssistantDialog(
                self,
                language=self.settings.value("language", "zh_CN", type=str),
            )
        if self._assistant_dialog.isVisible():
            self._assistant_dialog.hide()
            return
        self._assistant_dialog.show_near_button(self.assistant_button)

    def moveEvent(self, event):
        super().moveEvent(event)
        assistant_dialog = getattr(self, "_assistant_dialog", None)
        if assistant_dialog is not None and assistant_dialog.isVisible():
            assistant_dialog.position_near_button(self.assistant_button)

    def get_ai_catalog(self):
        """Return a compact, path-free game catalog as context for the local model."""
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id, name, category, tags, favorite, play_count FROM games ORDER BY name COLLATE NOCASE"
            ).fetchall()
        compact = []
        for row in rows[:180]:
            compact.append({
                "id": int(row["id"]),
                "name": str(row["name"] or ""),
                "category": str(row["category"] or "OTHER"),
                "tags": str(row["tags"] or "")[:100],
                "favorite": bool(row["favorite"]),
            })
        return {"total": len(rows), "games": compact, "truncated": len(rows) > len(compact)}

    def _ai_get_games(self):
        with db_connect() as conn:
            return conn.execute("SELECT * FROM games ORDER BY name COLLATE NOCASE").fetchall()

    def _ai_clean_query(self, query):
        value = str(query or "").strip()
        for pattern in (
            r"^(?:(?:请|麻烦|可以|能否|请问)\s*)?(?:帮我\s*)?(?:启动|打开|运行|游玩|玩一下|开始玩)(?:一下|下|游戏)?\s*",
            r"^(?:(?:please|can you|could you|would you)\s+)?(?:please\s+)?(?:(?:help me)\s+)?(?:launch|start|run|open|play)(?:\s+the game)?\s*",
            r"^(?:请问|请帮我|帮我|麻烦|请)?(?:搜索|查找|查询|找一下|找找|找|查看)\s*",
            r"^(?:please\s+)?(?:search(?:\s+for)?|find(?:\s+me)?|look\s+for)\s*",
        ):
            value = re.sub(pattern, "", value, flags=re.IGNORECASE)
        value = value.strip(" ：:，,。.!！?？\"'「」『』《》")
        value = re.sub(r"(?:游戏库里|我的游戏库里|游戏库中的|游戏库里的|里面的)?(?:游戏有哪些|有哪些游戏)$", "", value).strip()
        return value

    def _ai_category_code(self, query):
        cleaned = self._ai_clean_query(query).casefold().replace("游戏", "").strip()
        aliases = {
            "动作": "ACT", "action": "ACT", "冒险": "AVG", "adventure": "AVG",
            "角色扮演": "RPG", "roleplaying": "RPG", "role-playing": "RPG", "rpg": "RPG",
            "动作角色扮演": "ARPG", "arpg": "ARPG", "日式角色扮演": "JRPG", "jrpg": "JRPG",
            "大型多人在线": "MMORPG", "mmorpg": "MMORPG", "射击": "FPS", "fps": "FPS",
            "第一人称射击": "FPS", "第三人称射击": "TPS", "tps": "TPS", "策略": "SLG",
            "即时战略": "RTS", "rts": "RTS", "模拟": "SIM", "sim": "SIM",
            "竞速": "RAC", "赛车": "RAC", "rac": "RAC", "体育": "SPG", "spg": "SPG",
            "解谜": "PUZ", "puzzle": "PUZ", "moba": "MOBA", "肉鸽": "ROGUE",
            "roguelike": "ROGUE", "独立": "IND", "indie": "IND", "其他": "OTHER", "other": "OTHER",
        }
        if cleaned in aliases:
            return aliases[cleaned]
        known = {str(value).casefold(): str(value).upper() for value in CATEGORIES}
        return known.get(cleaned)

    def _ai_search_rows(self, query):
        """Search the whole local library, independent of the page currently selected."""
        cleaned = self._ai_clean_query(query)
        normalized = _normalize_search_text(cleaned)
        rows = self._ai_get_games()
        low = cleaned.casefold()

        favorite_terms = ("收藏", "favorites", "favorite", "favourites", "starred")
        recent_terms = ("最近玩过", "最近游玩", "最近启动", "recently played", "recent games", "last played")
        if any(term in low for term in favorite_terms):
            return [row for row in rows if bool(row["favorite"])], cleaned or "favorites"
        if any(term in low for term in recent_terms):
            recent = [row for row in rows if str(row["last_played"] or "").strip()]
            recent.sort(key=lambda row: str(row["last_played"] or ""), reverse=True)
            return recent, cleaned or "recent games"

        category = self._ai_category_code(cleaned)
        if category:
            found = [row for row in rows if str(row["category"] or "").casefold() == category.casefold()]
            return found, cleaned

        if not normalized:
            return [], cleaned
        ranked = []
        for row in rows:
            score = _fuzzy_search_score(
                cleaned,
                row["name"], row["category"], row["tags"], row["notes"], row["exe_path"],
            )
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _score, row in ranked], cleaned

    def _ai_format_games(self, rows, heading, max_items=24):
        total = len(rows)
        if not total:
            return heading + "\n" + ("目前游戏库是空的。先添加游戏或扫描游戏目录吧。" if self.settings.value("language", "zh_CN", type=str) != "en_US" else "Your game library is empty. Add a game or scan a folder first.")
        language = self.settings.value("language", "zh_CN", type=str)
        if language == "en_US":
            lines = [f"{heading} ({total} found):"]
            for index, row in enumerate(rows[:max_items], 1):
                details = [str(row["category"] or "OTHER")]
                if row["favorite"]:
                    details.append("Favorite")
                lines.append(f"{index}. {row['name']} · {' · '.join(details)}")
            if total > max_items:
                lines.append(f"Showing {max_items} of {total}. Narrow the search to see more.")
        else:
            lines = [f"{heading}（共 {total} 款）："]
            for index, row in enumerate(rows[:max_items], 1):
                details = [str(row["category"] or "OTHER")]
                if row["favorite"]:
                    details.append("已收藏")
                lines.append(f"{index}. {row['name']} · {' · '.join(details)}")
            if total > max_items:
                lines.append(f"仅显示前 {max_items} 款；可以继续按名称、分类或标签缩小范围。")
        return "\n".join(lines)

    def _ai_find_launch_candidates(self, query):
        cleaned = self._ai_clean_query(query)
        query_norm = _normalize_search_text(cleaned)
        if len(query_norm) < 2:
            return []
        candidates = []
        for row in self._ai_get_games():
            name = str(row["name"] or "")
            name_norm = _normalize_search_text(name)
            if query_norm == name_norm:
                score = 1.0
            elif query_norm and query_norm in name_norm:
                score = 0.98
            elif len(query_norm) >= 4 and abs(len(name_norm) - len(query_norm)) <= max(2, len(query_norm) // 3):
                # Launch matching is intentionally stricter than library search: use
                # whole-title similarity, not broad tag/path or character-overlap hits.
                score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
                if score < 0.76:
                    score = 0.0
            else:
                score = 0.0
            if score > 0:
                candidates.append((score, row))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates

    def _ai_explicit_launch_request(self, text):
        """Require a clear launch/play command before any game process is started."""
        value = str(text or "").strip().casefold()
        patterns = (
            r"^(?:(?:请|麻烦|可以|能否|请问)\s*)?(?:帮我\s*)?(?:启动|打开|运行|游玩|玩一下|开始玩)(?:一下|下|游戏)?",
            r"^(?:(?:please|can you|could you|would you)\s+)?(?:please\s+)?(?:(?:help me)\s+)?(?:launch|start|run|open|play)\b",
            r"^(?:我想|我要|想要|我想要)\s*(?:玩|启动|打开|运行)",
            r"^(?:i want to|i'd like to|i wanna)\s+(?:play|launch|start|run|open)\b",
        )
        return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)

    def handle_ai_action(self, action, query, model_reply="", original_text=""):
        """Validate and execute only the small set of app-level AI actions."""
        language = self.settings.value("language", "zh_CN", type=str)
        english = language == "en_US"
        if action == "list_games":
            rows = self._ai_get_games()
            return self._ai_format_games(
                rows,
                "Your Tutler game library" if english else "你的 Tutler 游戏库",
                max_items=30,
            )

        if action == "search_games":
            query = query or original_text
            rows, cleaned = self._ai_search_rows(query)
            if not rows:
                return (
                    f"No matching games found for “{cleaned}”. Try a title, category (RPG/FPS), or tag."
                    if english else
                    f"没有找到与「{cleaned}」匹配的游戏。可以尝试游戏名称、分类（如 RPG、FPS）或标签。"
                )
            heading = (f"Matches for “{cleaned}”" if english else f"「{cleaned}」的匹配结果")
            return self._ai_format_games(rows, heading, max_items=16)

        if action == "launch_game":
            if not self._ai_explicit_launch_request(original_text):
                return (
                    "I won't launch a game unless you clearly ask me to. Try ‘Launch Game Title’."
                    if english else
                    "为了避免误启动，请明确说出“启动/打开/玩 + 游戏名称”。当前消息没有被识别为明确的启动指令，所以没有启动任何游戏。"
                )
            query = query or original_text
            clean_target = self._ai_clean_query(query)
            generic_target = clean_target.casefold().strip() in {"游戏", "game", "a game", "the game", "any game", "任意游戏", "随便一款游戏"}
            if not clean_target or generic_target or self._ai_category_code(clean_target):
                return (
                    "Which game should I launch? Please include a specific game title, not just a genre."
                    if english else
                    "你想启动哪一款游戏？请提供具体游戏名称，而不是只说分类或“游戏”。"
                )
            candidates = self._ai_find_launch_candidates(clean_target)
            if not candidates or candidates[0][0] < 0.70:
                return (
                    f"I couldn't identify “{query}” in your Tutler library, so nothing was launched. Try the exact game title."
                    if english else
                    f"我没有在 Tutler 游戏库中明确找到「{query}」，因此没有启动任何游戏。请试试完整的游戏名称。"
                )
            best_score, best_row = candidates[0]
            if len(candidates) > 1 and best_score >= 0.90 and candidates[1][0] >= best_score - 0.035:
                names = "、".join(str(item[1]["name"]) for item in candidates[:4])
                return (
                    f"I found multiple close matches: {names}. Tell me which title you meant; I haven't launched anything."
                    if english else
                    f"找到多个相近的游戏名称：{names}。请告诉我具体要启动哪一款；我还没有启动任何游戏。"
                )
            launched = self.launch_game(int(best_row["id"]))
            if launched:
                return (
                    f"Sent the launch request for “{best_row['name']}”."
                    if english else
                    f"已向 Tutler 提交「{best_row['name']}」的启动请求。"
                )
            return (
                f"“{best_row['name']}” was not launched. The request may have been cancelled, its path may be invalid, or Steam may not be ready."
                if english else
                f"没有成功启动「{best_row['name']}」。可能是取消了启动确认、游戏路径无效，或 Steam 尚未准备好。"
            )

        return model_reply or ("我可以帮你查询或启动 Tutler 游戏库里的游戏。" if not english else "I can search your Tutler library or launch a game from it.")

    def _build_ui(self):
        # 外层使用自绘标题栏，主体仍保留原有 central widget 与全部业务布局。
        shell = QWidget()
        shell.setObjectName("WindowShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(1, 1, 1, 1)
        shell_layout.setSpacing(0)
        self.title_bar = ModernTitleBar(self)
        shell_layout.addWidget(self.title_bar)

        central = QWidget()
        central.setObjectName("Central")
        shell_layout.addWidget(central, 1)
        self.setCentralWidget(shell)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 左侧导航
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(246)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setFrameShape(QFrame.Shape.NoFrame)
        side_content = QWidget()
        side = QVBoxLayout(side_content)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(7)
        sidebar_layout.addWidget(side_scroll)

        logo_row = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("LogoMark")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(43, 43)
        if LOGO_PNG_PATH.exists():
            logo.setPixmap(QPixmap(str(LOGO_PNG_PATH)).scaled(43, 43, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_row.addWidget(logo)
        brand_col = QVBoxLayout()
        brand = QLabel("Tutler")
        brand.setObjectName("Brand")
        brand_sub = QLabel("GAME · VIDEO · IMAGE")
        brand_sub.setObjectName("BrandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        logo_row.addLayout(brand_col, 1)
        side.addLayout(logo_row)
        side.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.library_section_buttons = {}
        self.library_section_hosts = {}

        # 游戏库：VS Code / Visual Studio 风格的可折叠资源树
        game_header, game_host, game_layout = self._create_library_section("游戏库", "game", side, expanded=True)
        self.all_btn = self._add_nav_button("▦", "全部游戏", "all", game_layout, checked=True)
        self.fav_btn = self._add_nav_button("★", "我的收藏", "favorites", game_layout)
        # 游戏分类与「全部游戏」「我的收藏」同级；点击标题后才展开具体分类。
        self.category_section_btn = QPushButton("游戏分类")
        # 这是一个展开/折叠标题，不是页面导航项；不能呈现为与“全部游戏”同时选中的状态。
        # 与“全部游戏”等导航项使用相同样式、图标槽位和内边距；
        # 不加入 nav_group，因此它只是展开标题，不会被当作页面选中项。
        self.category_section_btn.setObjectName("NavButton")
        self.category_section_btn.setIcon(self._make_nav_icon("chevron-right"))
        self.category_section_btn.setProperty("nav_icon_glyph", "chevron-right")
        self.category_section_btn.setIconSize(QSize(18, 18))
        self.category_section_btn.setCheckable(False)
        self.category_section_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.category_section_btn.setMinimumHeight(38)
        # Match the navigation rows' geometry and typography exactly. Avoid a local
        # stylesheet here because it can override global NavButton padding/font rules.
        self.category_section_btn.setMinimumWidth(0)
        self.category_section_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.category_section_btn.setFont(self.all_btn.font())
        self._category_section_expanded = False
        game_layout.addWidget(self.category_section_btn)
        self.category_nav_host = QWidget()
        self.category_nav_host.setObjectName("CategoryNavHost")
        self.category_nav_host.setMaximumHeight(0)
        self.category_nav_host.setVisible(False)
        self._category_animation = None
        self.category_nav_layout = QVBoxLayout(self.category_nav_host)
        self.category_nav_layout.setContentsMargins(8, 0, 0, 0)
        self.category_nav_layout.setSpacing(5)
        self.category_section_btn.clicked.connect(self._toggle_category_section)
        for category in self._all_categories():
            self._add_category_nav_button(category)
        self.add_category_btn = QPushButton("＋  自定义分类")
        self.add_category_btn.setObjectName("NavButton")
        self.add_category_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_category_btn.setMinimumHeight(34)
        self.add_category_btn.clicked.connect(self.add_custom_category)
        self.manage_categories_btn = QPushButton("↕  排序/管理游戏分类")
        self.manage_categories_btn.setObjectName("NavButton")
        self.manage_categories_btn.setMinimumHeight(32)
        self.manage_categories_btn.clicked.connect(lambda: self.manage_categories("game"))
        self.category_nav_layout.addWidget(self.add_category_btn)
        self.category_nav_layout.addWidget(self.manage_categories_btn)
        game_layout.addWidget(self.category_nav_host)
        self._refresh_category_nav_order()

        # 视频库：只有激活视频库时显示其分类树
        video_header, video_host, video_layout = self._create_library_section("视频库", "video", side, expanded=False)
        self.video_btn = self._add_nav_button("▷", "全部视频", "videos", video_layout)
        self.video_category_nav_host = QWidget()
        self.video_category_nav_layout = QVBoxLayout(self.video_category_nav_host)
        self.video_category_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.video_category_nav_layout.setSpacing(5)
        self.add_video_category_btn = QPushButton("＋  自定义视频分类")
        self.add_video_category_btn.setObjectName("NavButton")
        self.add_video_category_btn.setMinimumHeight(32)
        self.add_video_category_btn.clicked.connect(self.add_custom_video_category)
        self.manage_video_categories_btn = QPushButton("↕  排序/管理视频分类")
        self.manage_video_categories_btn.setObjectName("NavButton")
        self.manage_video_categories_btn.setMinimumHeight(32)
        self.manage_video_categories_btn.clicked.connect(lambda: self.manage_categories("video"))
        self.video_category_nav_layout.addWidget(self.add_video_category_btn)
        self.video_category_nav_layout.addWidget(self.manage_video_categories_btn)
        for category in self._ordered_video_categories():
            self._add_video_category_nav_button(category)
        self._refresh_video_category_nav_order()
        video_layout.addWidget(self.video_category_nav_host)

        # 图片库
        image_header, image_host, image_layout = self._create_library_section("图片库", "image", side, expanded=False)
        self.image_btn = self._add_nav_button("▧", "全部图片", "images", image_layout)
        self.image_category_nav_host = QWidget()
        self.image_category_nav_layout = QVBoxLayout(self.image_category_nav_host)
        self.image_category_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.image_category_nav_layout.setSpacing(5)
        self.add_image_category_btn = QPushButton("＋  自定义图片分类")
        self.add_image_category_btn.setObjectName("NavButton")
        self.add_image_category_btn.setMinimumHeight(32)
        self.add_image_category_btn.clicked.connect(self.add_custom_image_category)
        self.manage_image_categories_btn = QPushButton("↕  排序/管理图片分类")
        self.manage_image_categories_btn.setObjectName("NavButton")
        self.manage_image_categories_btn.setMinimumHeight(32)
        self.manage_image_categories_btn.clicked.connect(lambda: self.manage_categories("image"))
        self.image_category_nav_layout.addWidget(self.add_image_category_btn)
        self.image_category_nav_layout.addWidget(self.manage_image_categories_btn)
        for category in self._ordered_image_categories():
            self._add_image_category_nav_button(category)
        self._refresh_image_category_nav_order()
        image_layout.addWidget(self.image_category_nav_host)

        side.addStretch(1)
        self.settings_btn = QPushButton("⚙    应用设置")
        self.settings_btn.setObjectName("NavButton")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setMinimumHeight(38)
        self.settings_btn.clicked.connect(self.open_settings)
        side.addWidget(self.settings_btn)
        side.addSpacing(8)
        side.addWidget(QLabel(f"Tutler {APP_VERSION}"))
        db_hint = QLabel("本机数据 · 离线可用")
        db_hint.setObjectName("BrandSub")
        side.addWidget(db_hint)

        side_scroll.setWidget(side_content)
        root.addWidget(sidebar)

        # 主内容区
        main_area = QWidget()
        main_area.setObjectName("MainArea")
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(30, 28, 30, 24)
        main_layout.setSpacing(20)

        header_row = QHBoxLayout()
        heading_col = QVBoxLayout()
        self.page_title = QLabel("全部游戏")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("管理并启动你电脑上的游戏")
        self.page_subtitle.setObjectName("Muted")
        heading_col.addWidget(self.page_title)
        heading_col.addWidget(self.page_subtitle)
        header_row.addLayout(heading_col, 1)

        self.add_btn = QPushButton("+ 添加游戏")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setFixedHeight(42)
        self.add_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.add_btn.clicked.connect(self.add_game)
        header_row.addWidget(self.add_btn)
        self.scan_btn = QPushButton("⌕  扫描目录")
        self.scan_btn.setFixedHeight(42)
        self.scan_btn.clicked.connect(self.scan_directory)
        header_row.addWidget(self.scan_btn)
        self.steam_btn = QPushButton("♨  识别 Steam")
        self.steam_btn.setFixedHeight(42)
        self.steam_btn.clicked.connect(self.scan_steam_games)
        header_row.addWidget(self.steam_btn)
        self.video_scan_btn = QPushButton("＋ 添加视频目录")
        self.video_scan_btn.setFixedHeight(42)
        self.video_scan_btn.clicked.connect(self.add_video_folder)
        self.video_scan_btn.setVisible(False)
        header_row.addWidget(self.video_scan_btn)
        self.image_scan_btn = QPushButton("＋ 添加图片目录")
        self.image_scan_btn.setFixedHeight(42)
        self.image_scan_btn.clicked.connect(self.add_image_folder)
        self.image_scan_btn.setVisible(False)
        header_row.addWidget(self.image_scan_btn)
        main_layout.addLayout(header_row)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchBox")
        self.search_edit.setPlaceholderText("⌕   搜索游戏名称、路径或标签…")
        # Debounce typing: don't rebuild thousands of cards for every keystroke.
        self._search_refresh_timer = QTimer(self)
        self._search_refresh_timer.setSingleShot(True)
        self._search_refresh_timer.setInterval(220)
        self._search_refresh_timer.timeout.connect(self.refresh_games)
        self.search_edit.textChanged.connect(self._schedule_search_refresh)
        toolbar.addWidget(self.search_edit, 1)

        self.sort_box = QComboBox()
        self.sort_box.addItems(["最近添加", "名称 A-Z", "最近游玩", "启动次数"])
        self.sort_box.currentTextChanged.connect(self.refresh_games)
        self.sort_box.setMinimumWidth(135)
        toolbar.addWidget(self.sort_box)
        self.import_btn = QPushButton("导入")
        self.import_btn.clicked.connect(self.import_csv)
        toolbar.addWidget(self.import_btn)
        self.export_btn = QPushButton("导出")
        self.export_btn.clicked.connect(self.export_csv)
        toolbar.addWidget(self.export_btn)
        main_layout.addLayout(toolbar)

        stats_row = QHBoxLayout()
        self.count_label = QLabel("0 款游戏")
        self.count_label.setObjectName("ResultsCount")
        stats_row.addWidget(self.count_label)
        stats_row.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        stats_row.addWidget(self.status_label)
        main_layout.addLayout(stats_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setObjectName("GameScroll")
        self.cards_host = QWidget()
        self.cards_host.setObjectName("CardsHost")
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(2, 2, 8, 8)
        self.cards_grid.setHorizontalSpacing(18)
        self.cards_grid.setVerticalSpacing(18)
        self.cards_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.cards_host)
        main_layout.addWidget(self.scroll, 1)
        root.addWidget(main_area, 1)

        # 本版移除顶部「文件 / 帮助」菜单，主要操作由界面按钮和应用设置入口提供。
        self._set_styles()

    def _load_custom_categories(self):
        saved = self.settings.value("custom_categories", [], type=list)
        return [str(item).strip() for item in saved if str(item).strip() and str(item).strip() not in CATEGORIES]

    def _load_custom_video_categories(self):
        saved = self.settings.value("custom_video_categories", [], type=list)
        return [str(item).strip() for item in saved if str(item).strip() and str(item).strip() not in VIDEO_DEFAULT_CATEGORIES]

    def _load_custom_image_categories(self):
        saved = self.settings.value("custom_image_categories", [], type=list)
        return [str(item).strip() for item in saved if str(item).strip()]

    def _all_categories(self):
        result = self._ordered_game_categories()
        # Retain any unexpected category already present in imported/older records.
        try:
            with db_connect() as conn:
                rows = conn.execute("SELECT DISTINCT category FROM games WHERE category IS NOT NULL AND TRIM(category) <> ''").fetchall()
            for row in rows:
                category = str(row[0]).strip()
                if category and category not in result:
                    result.append(category)
        except sqlite3.Error:
            pass
        return result

    def _ordered_game_categories(self):
        base = list(CATEGORIES) + [x for x in self.custom_categories if x not in CATEGORIES]
        try:
            with db_connect() as conn:
                rows = conn.execute("SELECT DISTINCT category FROM games WHERE category IS NOT NULL AND TRIM(category) <> ''").fetchall()
            for row in rows:
                category = str(row[0]).strip()
                if category and category not in base:
                    base.append(category)
        except sqlite3.Error:
            pass
        saved = self.settings.value("game_category_order", [], type=list)
        ordered = [x for x in saved if x in base]
        ordered.extend(x for x in base if x not in ordered)
        return ordered

    def _ordered_video_categories(self):
        base = list(VIDEO_DEFAULT_CATEGORIES) + [x for x in self.custom_video_categories if x not in VIDEO_DEFAULT_CATEGORIES]
        saved = self.settings.value("video_category_order", [], type=list)
        ordered = [x for x in saved if x in base]
        ordered.extend(x for x in base if x not in ordered)
        return ordered

    def _ordered_image_categories(self):
        base = list(IMAGE_DEFAULT_CATEGORIES) + [x for x in self.custom_image_categories if x not in IMAGE_DEFAULT_CATEGORIES]
        saved = self.settings.value("image_category_order", [], type=list)
        ordered = [x for x in saved if x in base]
        ordered.extend(x for x in base if x not in ordered)
        return ordered

    def _make_nav_icon(self, glyph):
        """Render navigation glyphs into a fixed-size pixmap so labels align exactly."""
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        # Icons are rasterized before/independently of stylesheet palette updates;
        # choose an explicit high-contrast color for the active theme.
        color = QColor("#dce4f2" if not self._is_light_theme() else "#46536a")
        color.setAlpha(245)
        painter.setPen(color)
        font = QFont()
        font.setPixelSize(14)
        font.setBold(True)
        painter.setFont(font)
        glyphs = {
            "chevron-right": "›", "chevron-down": "⌄",
            "grid": "▦", "star": "★", "dot": "•",
            "recent": "◷", "video": "▷", "image": "▧"
        }
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, glyphs.get(glyph, glyph))
        painter.end()
        return QIcon(pixmap)

    def _set_category_section_expanded(self, expanded):
        """只更新游戏分类子树的展开状态，不参与页面导航按钮的选中状态。"""
        host = getattr(self, "category_nav_host", None)
        if host is None:
            return
        self._category_section_expanded = bool(expanded)
        host.setVisible(self._category_section_expanded)
        host.setMaximumHeight(16777215 if self._category_section_expanded else 0)
        if self._category_section_expanded and host.layout() is not None:
            host.layout().invalidate()
            host.layout().activate()
        glyph = "chevron-down" if self._category_section_expanded else "chevron-right"
        self.category_section_btn.setProperty("nav_icon_glyph", glyph)
        self.category_section_btn.setIcon(self._make_nav_icon(glyph))

    def _toggle_category_section(self, _checked=False):
        self._set_category_section_expanded(not self._category_section_expanded)

    def _add_category_nav_button(self, category):
        if category in self.category_nav_buttons:
            return
        btn = self._add_nav_button("•", category, "category:" + category, self.category_nav_layout)
        btn.setToolTip(f"显示「{category}」分类中的游戏")
        self.category_nav_buttons[category] = btn
        self._refresh_category_nav_order()

    def _refresh_category_nav_order(self):
        if not hasattr(self, "category_nav_layout") or not hasattr(self, "add_category_btn"):
            return
        for btn in self.category_nav_buttons.values():
            self.category_nav_layout.removeWidget(btn)
        self.category_nav_layout.removeWidget(self.add_category_btn)
        if hasattr(self, "manage_categories_btn"):
            self.category_nav_layout.removeWidget(self.manage_categories_btn)
        for category in self._ordered_game_categories():
            btn = self.category_nav_buttons.get(category)
            if btn:
                self.category_nav_layout.addWidget(btn)
        self.category_nav_layout.addWidget(self.add_category_btn)
        if hasattr(self, "manage_categories_btn"):
            self.category_nav_layout.addWidget(self.manage_categories_btn)

    def _add_video_category_nav_button(self, category):
        if category in self.video_category_nav_buttons:
            return
        btn = self._add_nav_button("•", category, "video_category:" + category, self.video_category_nav_layout)
        btn.setToolTip(f"显示「{category}」视频分类")
        self.video_category_nav_buttons[category] = btn
        self._refresh_video_category_nav_order()

    def _refresh_video_category_nav_order(self):
        if not hasattr(self, "video_category_nav_layout") or not hasattr(self, "add_video_category_btn") or not hasattr(self, "manage_video_categories_btn"):
            return
        for btn in self.video_category_nav_buttons.values():
            self.video_category_nav_layout.removeWidget(btn)
        self.video_category_nav_layout.removeWidget(self.add_video_category_btn)
        self.video_category_nav_layout.removeWidget(self.manage_video_categories_btn)
        for category in self._ordered_video_categories():
            btn = self.video_category_nav_buttons.get(category)
            if btn:
                self.video_category_nav_layout.addWidget(btn)
        self.video_category_nav_layout.addWidget(self.add_video_category_btn)
        self.video_category_nav_layout.addWidget(self.manage_video_categories_btn)

    def _add_image_category_nav_button(self, category):
        if category in self.image_category_nav_buttons:
            return
        btn = self._add_nav_button("•", category, "image_category:" + category, self.image_category_nav_layout)
        btn.setToolTip(f"显示「{category}」图片分类")
        self.image_category_nav_buttons[category] = btn
        self._refresh_image_category_nav_order()

    def _refresh_image_category_nav_order(self):
        if not hasattr(self, "image_category_nav_layout") or not hasattr(self, "add_image_category_btn") or not hasattr(self, "manage_image_categories_btn"):
            return
        for btn in self.image_category_nav_buttons.values():
            self.image_category_nav_layout.removeWidget(btn)
        self.image_category_nav_layout.removeWidget(self.add_image_category_btn)
        self.image_category_nav_layout.removeWidget(self.manage_image_categories_btn)
        for category in self._ordered_image_categories():
            btn = self.image_category_nav_buttons.get(category)
            if btn:
                self.image_category_nav_layout.addWidget(btn)
        self.image_category_nav_layout.addWidget(self.add_image_category_btn)
        self.image_category_nav_layout.addWidget(self.manage_image_categories_btn)

    def add_custom_category(self):
        name, accepted = QInputDialog.getText(self, "新增游戏分类", "请输入分类名称（如 SURVIVAL、SANDBOX）：")
        if not accepted:
            return
        name = name.strip().upper()
        if not name:
            QMessageBox.information(self, "分类名称不能为空", "请输入一个分类名称。")
            return
        if name in self._all_categories():
            QMessageBox.information(self, "分类已存在", f"「{name}」已经存在，无需重复添加。")
            return
        self.custom_categories.append(name)
        self.settings.setValue("custom_categories", self.custom_categories)
        self.settings.sync()
        self._add_category_nav_button(name)
        self.category_nav_buttons[name].setChecked(True)
        self.change_view("category:" + name)

    def add_custom_video_category(self):
        name, accepted = QInputDialog.getText(self, "新增视频分类", "请输入视频分类名称：")
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.information(self, "分类名称不能为空", "请输入一个分类名称。")
            return
        if name in self._ordered_video_categories():
            QMessageBox.information(self, "分类已存在", f"「{name}」已经存在。")
            return
        self.custom_video_categories.append(name)
        self.settings.setValue("custom_video_categories", self.custom_video_categories)
        self.settings.sync()
        self._add_video_category_nav_button(name)
        self.video_category_nav_buttons[name].setChecked(True)
        self.change_view("video_category:" + name)

    def add_custom_image_category(self):
        name, accepted = QInputDialog.getText(self, "新增图片分类", "请输入图片分类名称：")
        if not accepted:
            return
        name = name.strip()
        if not name:
            QMessageBox.information(self, "分类名称不能为空", "请输入一个分类名称。")
            return
        if name in self._ordered_image_categories():
            QMessageBox.information(self, "分类已存在", f"「{name}」已经存在。")
            return
        self.custom_image_categories.append(name)
        self.settings.setValue("custom_image_categories", self.custom_image_categories)
        self.settings.sync()
        self._add_image_category_nav_button(name)
        self.image_category_nav_buttons[name].setChecked(True)
        self.change_view("image_category:" + name)

    def manage_categories(self, kind):
        is_video = kind == "video"
        is_image = kind == "image"
        defaults = list(VIDEO_DEFAULT_CATEGORIES if is_video else IMAGE_DEFAULT_CATEGORIES if is_image else CATEGORIES)
        if is_video:
            title = "视频分类排序与管理"
            custom = self.custom_video_categories
            ordered = self._ordered_video_categories()
        elif is_image:
            title = "图片分类排序与管理"
            custom = self.custom_image_categories
            ordered = self._ordered_image_categories()
        else:
            title = "游戏分类排序与管理"
            custom = self.custom_categories
            ordered = self._ordered_game_categories()

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(440, 480)
        layout = QVBoxLayout(dialog)
        intro = QLabel("选中分类后使用上移/下移调整左侧顺序。自定义分类可删除；删除分类不会删除媒体或游戏文件。视频库和图片库默认没有预置分类。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        listing = QListWidget()
        for category in ordered:
            item = QListWidgetItem(category)
            item.setToolTip("内置分类（不可删除）" if category in defaults else "自定义分类")
            listing.addItem(item)
        layout.addWidget(listing, 1)

        buttons = QHBoxLayout()
        up_btn = QPushButton("上移")
        down_btn = QPushButton("下移")
        delete_btn = QPushButton("删除自定义分类")
        reset_btn = QPushButton("恢复默认设置")
        buttons.addWidget(up_btn)
        buttons.addWidget(down_btn)
        buttons.addWidget(delete_btn)
        layout.addLayout(buttons)
        layout.addWidget(reset_btn)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(box)

        def move_item(delta):
            row = listing.currentRow()
            target = row + delta
            if row < 0 or target < 0 or target >= listing.count():
                return
            item = listing.takeItem(row)
            listing.insertItem(target, item)
            listing.setCurrentRow(target)

        def delete_item():
            row = listing.currentRow()
            if row < 0:
                QMessageBox.information(dialog, "请选择分类", "请先选择要删除的分类。")
                return
            name = listing.item(row).text()
            if name in defaults:
                QMessageBox.information(dialog, "不能删除", "内置分类不能删除。")
                return
            # Use a purpose-built confirmation dialog instead of QMessageBox: native
            # QMessageBox label geometry/style can shift under Windows light mode.
            confirm = QDialog(dialog)
            confirm.setObjectName("DeleteCategoryConfirmDialog")
            confirm.setWindowTitle("确认删除自定义分类")
            confirm.setModal(True)
            confirm.setMinimumWidth(440)
            confirm.setMaximumWidth(520)
            confirm_layout = QVBoxLayout(confirm)
            confirm_layout.setContentsMargins(24, 22, 24, 18)
            confirm_layout.setSpacing(14)

            title_label = QLabel("确认删除自定义分类")
            title_label.setObjectName("DeleteCategoryTitle")
            title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            title_label.setWordWrap(True)
            confirm_layout.addWidget(title_label)

            question_label = QLabel(f"确定删除分类「{name}」吗？")
            question_label.setObjectName("DeleteCategoryQuestion")
            question_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            question_label.setWordWrap(True)
            confirm_layout.addWidget(question_label)

            if is_video or is_image:
                detail_text = "该分类下的资源将变为无分类。只删除分类设置，不会删除硬盘上的文件。"
            else:
                detail_text = "该分类下的游戏将移至 OTHER。只删除分类设置，不会删除游戏文件。"
            detail_label = QLabel(detail_text)
            detail_label.setObjectName("DeleteCategoryDetail")
            detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            detail_label.setWordWrap(True)
            confirm_layout.addWidget(detail_label)

            confirm_layout.addSpacing(4)
            confirm_buttons = QHBoxLayout()
            confirm_buttons.setSpacing(10)
            confirm_buttons.addStretch(1)
            cancel_button = QPushButton("取消")
            cancel_button.setObjectName("DeleteCategoryCancelButton")
            cancel_button.setMinimumWidth(92)
            delete_button = QPushButton("删除分类")
            delete_button.setObjectName("DeleteCategoryDangerButton")
            delete_button.setMinimumWidth(100)
            confirm_buttons.addWidget(cancel_button)
            confirm_buttons.addWidget(delete_button)
            confirm_layout.addLayout(confirm_buttons)

            app_instance = QApplication.instance()
            is_dark_theme = bool(app_instance.property("gameshelf_dark_mode")) if app_instance else False
            dialog_text_color = "#f1f3fa" if is_dark_theme else "#20283a"
            dialog_secondary_color = "#d0d5e1" if is_dark_theme else "#4b5568"
            dialog_bg_color = "#191e29" if is_dark_theme else "#ffffff"
            dialog_border_color = "#343d50" if is_dark_theme else "#d6dce7"
            input_bg_color = "#232a38" if is_dark_theme else "#f5f7fb"
            # Set both stylesheet and palette explicitly. A dialog-local stylesheet can
            # otherwise override the app stylesheet and leave Windows' default dark
            # palette in place, making the light-theme dialog look like a black block.
            confirm.setAutoFillBackground(True)
            confirm.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            confirm_palette = confirm.palette()
            confirm_palette.setColor(QPalette.ColorRole.Window, QColor(dialog_bg_color))
            confirm_palette.setColor(QPalette.ColorRole.WindowText, QColor(dialog_text_color))
            confirm_palette.setColor(QPalette.ColorRole.Base, QColor(dialog_bg_color))
            confirm_palette.setColor(QPalette.ColorRole.Text, QColor(dialog_text_color))
            confirm.setPalette(confirm_palette)
            confirm.setStyleSheet(f"""
                QDialog#DeleteCategoryConfirmDialog {{
                    background-color: {dialog_bg_color}; color: {dialog_text_color};
                    border: 1px solid {dialog_border_color}; border-radius: 12px;
                }}
                QDialog#DeleteCategoryConfirmDialog QWidget {{
                    color: {dialog_text_color}; background-color: transparent;
                    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                }}
                QLabel#DeleteCategoryTitle {{ color: {dialog_text_color}; background-color: transparent; font-size: 16px; font-weight: 700; margin: 0; padding: 0; }}
                QLabel#DeleteCategoryQuestion {{ color: {dialog_text_color}; background-color: transparent; font-size: 14px; font-weight: 600; margin: 0; padding: 0; }}
                QLabel#DeleteCategoryDetail {{ color: {dialog_secondary_color}; background-color: transparent; font-size: 13px; margin: 0; padding: 0; }}
                QPushButton#DeleteCategoryDangerButton {{
                    color: #ffffff; background-color: #b42318; border: 1px solid #b42318;
                    border-radius: 8px; padding: 8px 14px; min-height: 18px; font-weight: 700;
                }}
                QPushButton#DeleteCategoryDangerButton:hover {{ background-color: #912018; border-color: #912018; }}
                QPushButton#DeleteCategoryCancelButton {{
                    color: {dialog_text_color}; background-color: {input_bg_color};
                    border: 1px solid {dialog_border_color}; border-radius: 8px;
                    padding: 8px 14px; min-height: 18px; font-weight: 600;
                }}
                QPushButton#DeleteCategoryCancelButton:hover {{ background-color: {dialog_border_color}; }}
                QPushButton#DeleteCategoryCancelButton:focus {{ border: 1px solid #5b7cfa; }}
            """)
            cancel_button.setDefault(True)
            cancel_button.clicked.connect(confirm.reject)
            delete_button.clicked.connect(confirm.accept)
            if confirm.exec() != QDialog.DialogCode.Accepted:
                return
            listing.takeItem(row)
            # Defer actual deletion until Save; Cancel must leave all settings untouched.
            if listing.count() > 0:
                listing.setCurrentRow(min(row, listing.count() - 1))

        def reset_order():
            listing.clear()
            current_custom = self.custom_video_categories if is_video else self.custom_image_categories if is_image else self.custom_categories
            for category in defaults + [x for x in current_custom if x not in defaults]:
                listing.addItem(category)
            if listing.count():
                listing.setCurrentRow(0)

        up_btn.clicked.connect(lambda: move_item(-1))
        down_btn.clicked.connect(lambda: move_item(1))
        delete_btn.clicked.connect(delete_item)
        reset_btn.clicked.connect(reset_order)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_order = [listing.item(i).text() for i in range(listing.count())]
            removed = [name for name in ordered if name not in new_order]
            if is_video:
                self.custom_video_categories = [x for x in self.custom_video_categories if x not in removed]
                for path, category in list(self.video_category_map.items()):
                    if category in removed:
                        self.video_category_map[path] = ""
                self.settings.setValue("custom_video_categories", self.custom_video_categories)
                self.settings.setValue("video_category_map", self.video_category_map)
                for name in removed:
                    btn = self.video_category_nav_buttons.pop(name, None)
                    if btn:
                        self.nav_group.removeButton(btn); self.video_category_nav_layout.removeWidget(btn); btn.deleteLater()
            elif is_image:
                self.custom_image_categories = [x for x in self.custom_image_categories if x not in removed]
                for path, category in list(self.image_category_map.items()):
                    if category in removed:
                        self.image_category_map[path] = ""
                self.settings.setValue("custom_image_categories", self.custom_image_categories)
                self.settings.setValue("image_category_map", self.image_category_map)
                for name in removed:
                    btn = self.image_category_nav_buttons.pop(name, None)
                    if btn:
                        self.nav_group.removeButton(btn); self.image_category_nav_layout.removeWidget(btn); btn.deleteLater()
            else:
                self.custom_categories = [x for x in self.custom_categories if x not in removed]
                self.settings.setValue("custom_categories", self.custom_categories)
                if removed:
                    placeholders = ",".join("?" for _ in removed)
                    with db_connect() as conn:
                        conn.execute(f"UPDATE games SET category='OTHER' WHERE category IN ({placeholders})", removed)
                for name in removed:
                    btn = self.category_nav_buttons.pop(name, None)
                    if btn:
                        self.nav_group.removeButton(btn); self.category_nav_layout.removeWidget(btn); btn.deleteLater()
            key = "video_category_order" if is_video else "image_category_order" if is_image else "game_category_order"
            # Persist an order containing only categories that still exist. This prevents
            # deleted names from reappearing after restart due to stale settings.
            if is_video:
                valid_categories = set(VIDEO_DEFAULT_CATEGORIES + self.custom_video_categories)
            elif is_image:
                valid_categories = set(IMAGE_DEFAULT_CATEGORIES + self.custom_image_categories)
            else:
                valid_categories = set(self._ordered_game_categories())
            saved_order = [name for name in new_order if name in valid_categories]
            self.settings.setValue(key, saved_order)
            self.settings.sync()
            if removed and ((is_video and self.current_view in {"video_category:" + n for n in removed}) or (is_image and self.current_view in {"image_category:" + n for n in removed}) or (not is_video and not is_image and self.current_view in {"category:" + n for n in removed})):
                self.change_view("videos" if is_video else "images" if is_image else "all")
            if removed:
                self.show_toast("分类已删除", f"已删除 {len(removed)} 个自定义分类，相关资源已移至无分类/默认分类。")
            elif new_order != ordered:
                self.show_toast("分类排序已保存", "分类顺序已更新并保存，没有删除分类。")
            else:
                self.show_toast("没有删除分类", "本次没有删除任何分类，分类设置未发生变化。")
        if is_video:
            self._refresh_video_category_nav_order()
            self.refresh_videos()
        elif is_image:
            self._refresh_image_category_nav_order()
            self.refresh_images()
        else:
            self._refresh_category_nav_order()
            self.refresh_games()

    def _add_nav_button(self, icon_text, label, view, layout, checked=False):
        btn = QPushButton(label)
        btn.setObjectName("NavButton")
        icon_key = {"▦": "grid", "★": "star", "•": "dot", "◷": "recent", "▷": "video", "▧": "image"}.get(icon_text, icon_text)
        btn.setProperty("nav_icon_glyph", icon_key)
        btn.setIcon(self._make_nav_icon(icon_key))
        btn.setIconSize(QSize(18, 18))
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(lambda _checked=False, v=view: self.change_view(v))
        self.nav_group.addButton(btn)
        self.nav_buttons.append(btn)
        layout.addWidget(btn)
        return btn

    def _create_library_section(self, title, key, parent_layout, expanded=False):
        header = QPushButton(("▾" if expanded else "▸") + "  " + title)
        header.setObjectName("SectionLabel")
        header.setCheckable(True)
        header.setChecked(expanded)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setFlat(True)
        parent_layout.addWidget(header)
        host = QWidget()
        content_layout = QVBoxLayout(host)
        content_layout.setContentsMargins(8, 0, 0, 0)
        content_layout.setSpacing(5)
        host.setVisible(expanded)
        if not expanded:
            host.setMaximumHeight(0)
        parent_layout.addWidget(host)
        self.library_section_buttons[key] = header
        self.library_section_hosts[key] = host
        header.toggled.connect(lambda checked, k=key: self._toggle_library_section(k, checked))
        # Opening a library header always starts at that library's root page
        # (All Games / All Videos / All Images), not the last-used subcategory.
        header.clicked.connect(
            lambda _checked=False, k=key: self._on_library_header_clicked(k)
            if header.isChecked() else None
        )
        return header, host, content_layout

    def _animate_expandable(self, widget, expanded, animation_key, duration=190):
        """高度动画使用当前 maximumHeight 作为起点，支持中途反向和快速切换。"""
        if widget is None:
            return
        if not hasattr(self, "_expand_animations"):
            self._expand_animations = {}

        animations = self._expand_animations
        previous = animations.get(animation_key)
        # maximumHeight 正是动画属性；在 stop 前读取它，避免重新从 0 开始。
        current_limit = widget.maximumHeight()
        current_height = max(0, min(widget.height(), current_limit)) if widget.isVisible() else 0
        if previous is not None:
            current_height = max(0, current_limit if current_limit < 16777215 else current_height)
            previous.stop()
            animations.pop(animation_key, None)

        layout = widget.layout()
        if expanded:
            widget.setVisible(True)
            widget.setMaximumHeight(16777215)
            widget.ensurePolished()
            if layout is not None:
                layout.invalidate()
                layout.activate()
            target_height = max(1, widget.sizeHint().height(), layout.sizeHint().height() if layout else 0)
            start_height = min(current_height, target_height) if current_height > 0 else 0
            end_height = target_height
        else:
            # 若控件已在收起动画中，使用动画当前值；否则按当前实际高度收起。
            start_height = current_height
            if start_height <= 0 and widget.isVisible():
                start_height = max(0, widget.sizeHint().height())
            if start_height <= 0:
                widget.setVisible(False)
                widget.setMaximumHeight(16777215)
                return
            end_height = 0
            widget.setVisible(True)

        widget.setMaximumHeight(start_height)
        animation = QPropertyAnimation(widget, b"maximumHeight", self)
        animation.setDuration(duration)
        animation.setStartValue(start_height)
        animation.setEndValue(end_height)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic if expanded else QEasingCurve.Type.InCubic)

        def finish():
            # 仅当前动画可以提交最终状态，旧动画绝不能重新显示已切走的 UI。
            if animations.get(animation_key) is not animation:
                animation.deleteLater()
                return
            animations.pop(animation_key, None)
            widget.setMaximumHeight(16777215)
            widget.setVisible(bool(expanded))
            animation.deleteLater()

        animation.finished.connect(finish)
        animations[animation_key] = animation
        animation.start()

    def _set_library_header(self, key, checked):
        header = self.library_section_buttons.get(key)
        if header is None:
            return
        header.blockSignals(True)
        header.setChecked(checked)
        title = {"game": "游戏库", "video": "视频库", "image": "图片库"}.get(key, key)
        header.setText(("▾" if checked else "▸") + "  " + title)
        header.blockSignals(False)

    def _toggle_library_section(self, key, expanded):
        """资源库互斥展开：切换时先彻底隐藏旧库，只动画新打开的父容器。"""
        if key not in self.library_section_hosts:
            return

        animations = getattr(self, "_expand_animations", {})
        target_host = self.library_section_hosts[key]

        # 同步标题状态时阻断信号，避免 setChecked 重新进入本函数。
        for section_key in self.library_section_hosts:
            self._set_library_header(section_key, section_key == key and expanded)

        # 停止所有旧库动画并立即隐藏非目标库。旧库不再边收起边显示内容，
        # 避免“全部图片”等子控件在左侧残留，也避免多个大布局同时重排导致卡顿。
        for section_key, host in self.library_section_hosts.items():
            animation_key = f"library:{section_key}"
            old_animation = animations.pop(animation_key, None)
            if old_animation is not None:
                old_animation.stop()
                old_animation.deleteLater()

            if section_key != key or not expanded:
                host.setVisible(False)
                host.setMaximumHeight(16777215)

        if not expanded:
            target_host.setVisible(False)
            target_host.setMaximumHeight(16777215)
            return

        # 如果目标库已经完整展开，不要因为 change_view 的重复调用重新播放动画。
        active_animation = animations.get(f"library:{key}")
        if target_host.isVisible() and active_animation is None:
            target_host.setMaximumHeight(16777215)
            return

        # 新库独立展开；分类树不做子级高度动画，避免父子动画相互抢布局。
        target_host.setVisible(True)
        target_host.setMaximumHeight(0)
        layout = target_host.layout()
        target_host.ensurePolished()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        target_height = max(
            1,
            target_host.sizeHint().height(),
            layout.sizeHint().height() if layout is not None else 0,
        )

        animation = QPropertyAnimation(target_host, b"maximumHeight", self)
        animation.setDuration(190)
        animation.setStartValue(0)
        animation.setEndValue(target_height)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation_key = f"library:{key}"

        def finish():
            if animations.get(animation_key) is not animation:
                animation.deleteLater()
                return
            animations.pop(animation_key, None)
            target_host.setMaximumHeight(16777215)
            target_host.setVisible(True)
            animation.deleteLater()

        animation.finished.connect(finish)
        animations[animation_key] = animation
        animation.start()

    def _activate_library_section(self, key):
        """由视图切换调用，保证资源库展开状态与当前视图一致。"""
        if key not in self.library_section_hosts:
            key = "game"
        self._toggle_library_section(key, True)

    def _on_library_header_clicked(self, key):
        """打开资源库时进入该库的根页面；折叠操作不改变当前页面。"""
        root_view = {"game": "all", "video": "videos", "image": "images"}.get(key, "all")
        # Root pages should show the whole library, not retain a prior search filter.
        if self.search_edit.text():
            self.search_edit.clear()
        self.change_view(root_view)

    def _schedule_search_refresh(self, *_):
        """Delay filtering until typing pauses, keeping the UI responsive."""
        timer = getattr(self, "_search_refresh_timer", None)
        if timer is not None:
            timer.start()
        else:
            self.refresh_games()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("文件")
        for text, callback in [
            ("添加游戏", self.add_game),
            ("扫描游戏目录", self.scan_directory),
            ("导入 CSV 清单", self.import_csv),
            ("导出 CSV 清单", self.export_csv),
        ]:
            action = QAction(text, self)
            action.triggered.connect(callback)
            file_menu.addAction(action)
        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.exit_application)
        file_menu.addAction(exit_action)

        settings_action = QAction("应用设置…", self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addSeparator()
        file_menu.addAction(settings_action)

        help_menu = self.menuBar().addMenu("帮助")
        about_action = QAction("关于 Tutler", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _set_styles(self):
        """统一主题、文字对比度、对话框和控件圆角。"""
        accent = QColor(self.accent_color)
        accent_hex = accent.name()
        accent_hover = accent.lighter(115).name()
        accent_soft = accent.darker(185).name()

        light = self._is_light_theme()
        # In light mode, a lightened accent can become nearly white on the selected tab.
        # Use a darker accent for readable selected-tab text instead.
        accent_text = accent.darker(150).name() if light else accent.lighter(145).name()
        if light:
            c = {
                "window": "#f5f7fb", "sidebar": "#edf1f7", "panel": "#f7f9fc",
                "card": "#ffffff", "border": "#dce3ed", "border_strong": "#c5cfde",
                "text": "#20283a", "secondary": "#3e4a60", "muted": "#59677e",
                "subtle": "#637087", "input": "#ffffff", "button": "#ffffff",
                "button_hover": "#e9edf5", "cover": "#e8edf5", "tag_bg": "#ece9ff",
                "tag_text": "#5145a6", "nav_hover": "#dce4f0", "nav_active": "#e4e0ff",
                "dialog": "#f5f7fb", "tab": "#e9edf5", "scroll_bg": "#edf0f5",
                "scroll_handle": "#c5ccda", "tooltip": "#ffffff", "shadow_border": "#d5dce7",
                "favorite_bg": "#f1f2f8", "favorite_text": "#5145a6",
            }
        else:
            c = {
                "window": "#101218", "sidebar": "#151820", "panel": "#171b24",
                "card": "#191e28", "border": "#2d3444", "border_strong": "#424c61",
                "text": "#f1f3fa", "secondary": "#d0d5e1", "muted": "#b0bacb",
                "subtle": "#a6b0c3", "input": "#1c2230", "button": "#232a38",
                "button_hover": "#30394b", "cover": "#252c3c", "tag_bg": "#282545",
                "tag_text": "#c4bcff", "nav_hover": "#252b39", "nav_active": "#302b50",
                "dialog": "#191e29", "tab": "#202635", "scroll_bg": "#151922",
                "scroll_handle": "#414b60", "tooltip": "#252c3b", "shadow_border": "#343d50",
                "favorite_bg": "#252a3a", "favorite_text": "#d0c9ff",
            }

        # 让 Windows 原生标题栏、窗口边框与 Qt 客户区使用同一套主题颜色。
        app = QApplication.instance()
        if app is not None:
            app.setProperty("gameshelf_dark_mode", not light)
            app.setProperty("gameshelf_caption_color", c["window"])
            app.setProperty("gameshelf_dialog_caption_color", c["dialog"])
            app.setProperty("gameshelf_border_color", c["border"])
            app.setProperty("gameshelf_title_text_color", c["text"])

        # 强调色应用到选中项、主要按钮和焦点边框；正文颜色不依赖强调色亮度。
        stylesheet = f"""
            QWidget {{
                color: {c['text']};
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
                font-size: 13px;
            }}
            QMainWindow, QWidget#Central, QWidget#MainArea, QWidget#CardsHost {{
                background-color: {c['window']};
            }}
            QDialog, QMessageBox {{
                background-color: {c['dialog']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 14px;
            }}
            QDialog > QWidget, QMessageBox > QWidget {{ background-color: transparent; }}
            QDialog QLabel {{ color: {c['text']}; background-color: transparent; }}
            QDialog QCheckBox {{ color: {c['text']}; background-color: transparent; }}
            QDialog QComboBox, QDialog QLineEdit, QDialog QTextEdit {{
                color: {c['text']}; background-color: {c['input']};
            }}
            QDialog QComboBox QAbstractItemView {{
                color: {c['text']}; background-color: {c['panel']};
                selection-color: {c['text']}; selection-background-color: {c['nav_active']};
            }}
            QFrame#Sidebar {{
                background-color: {c['sidebar']};
                border-right: 1px solid {c['border']};
            }}
            QLabel#LogoMark {{
                background-color: {accent_hex}; color: #ffffff; border-radius: 12px;
                font-size: 18px; font-weight: 800;
            }}
            QLabel#Brand {{ font-size: 19px; font-weight: 750; color: {c['text']}; }}
            QLabel#BrandSub {{ color: {c['muted']}; font-size: 10px; letter-spacing: 1px; }}
            QLabel#SectionLabel {{
                color: {c['muted']}; font-size: 11px; font-weight: 750;
                padding-top: 7px; padding-bottom: 4px;
            }}
            QPushButton#SectionLabel {{
                color: {c['secondary']}; background: transparent; border: none;
                border-radius: 6px; text-align: left; font-size: 12px; font-weight: 800;
                padding: 8px 7px; min-height: 16px;
            }}
            QPushButton#SectionLabel:hover {{ color: {c['text']}; background-color: {c['button_hover']}; }}
            QPushButton#SectionLabel:checked {{ color: {accent_hover}; }}
            QProgressBar#ScanProgress {{ background-color: {c['border']}; border: none; border-radius: 2px; }}
            QProgressBar#ScanProgress::chunk {{ background-color: {accent_hex}; border-radius: 2px; }}
            QLabel#PageTitle {{ font-size: 27px; font-weight: 750; color: {c['text']}; }}
            QLabel#Muted {{ color: {c['muted']}; font-size: 12px; }}
            QLabel#ResultsCount {{ color: {c['secondary']}; font-size: 12px; font-weight: 700; }}
            QLabel#Hint {{ color: {c['muted']}; font-size: 11px; }}
            QLabel#CardTitle {{ font-size: 15px; font-weight: 700; color: {c['text']}; }}
            QLabel#PathLabel {{ color: {c['muted']}; font-size: 10px; }}
            QLabel#TagsLabel {{
                color: {c['tag_text']}; background-color: {c['tag_bg']};
                border: 1px solid {c['border']}; border-radius: 6px;
                padding: 4px 7px; font-size: 10px;
            }}
            QPushButton#NavButton {{
                text-align: left; padding: 10px 12px; border: 1px solid transparent;
                background-color: transparent; color: {c['secondary']}; border-radius: 10px;
            }}
            QPushButton#NavButton:hover {{ background-color: {c['nav_hover']}; color: {c['text']}; }}
            QPushButton#NavButton:checked {{
                background-color: {c['nav_active']}; color: {c['text']}; font-weight: 750;
                border: 1px solid {accent_hex}; border-left: 4px solid {accent_hex}; padding-left: 8px;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background-color: {c['input']}; color: {c['text']};
                border: 1px solid {c['border_strong']}; border-radius: 10px;
                padding: 9px 11px; selection-background-color: {accent_hex};
                selection-color: #ffffff;
            }}
            QLineEdit::placeholder {{ color: {c['muted']}; }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border: 1px solid {accent_hover}; }}
            QComboBox {{ padding-right: 25px; }}
            QComboBox::drop-down {{ border: none; width: 24px; border-top-right-radius: 9px; border-bottom-right-radius: 9px; }}
            QComboBox QAbstractItemView {{
                background-color: {c['panel']}; color: {c['text']};
                selection-background-color: {c['nav_active']};
                selection-color: {c['text']}; border: 1px solid {c['border']};
                border-radius: 8px; padding: 4px; outline: 0;
            }}
            QPushButton {{
                background-color: {c['button']}; color: {c['text']};
                border: 1px solid {c['border_strong']}; border-radius: 10px;
                padding: 9px 13px; min-height: 18px;
            }}
            QPushButton:hover {{ background-color: {c['button_hover']}; border-color: {accent_hover}; }}
            QPushButton:pressed {{ padding-top: 10px; padding-bottom: 8px; }}
            QPushButton:disabled {{ color: {c['muted']}; background-color: {c['panel']}; border-color: {c['border']}; }}
            QPushButton#PrimaryButton {{
                background-color: {accent_hex}; border: 1px solid {accent_hex};
                color: #ffffff; font-weight: 750; padding: 10px 15px;
            }}
            QPushButton#PrimaryButton:hover {{ background-color: {accent_hover}; border-color: {accent_hover}; }}
            QFrame#GameCard {{
                background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 15px;
            }}
            QFrame#GameCard:hover {{ border: 1px solid {accent_hex}; background-color: {c['panel']}; }}
            QFrame#CoverBox {{ background-color: {c['cover']}; border: none; border-radius: 10px; }}
            QLabel#CoverImage {{ background-color: {c['cover']}; border-radius: 10px; }}
            QLabel#CoverPlaceholder {{
                background-color: {c['cover']}; color: {c['muted']}; font-size: 17px;
                font-weight: 700; border-radius: 10px;
            }}
            QPushButton#FavoriteButton {{
                color: {c['favorite_text']}; font-size: 19px; background-color: {c['favorite_bg']};
                border: 1px solid transparent; border-radius: 9px; padding: 2px;
            }}
            QPushButton#FavoriteButton:hover {{ background-color: {c['nav_active']}; }}
            QLabel#CoverPreview {{ background-color: {c['cover']}; color: {c['muted']}; border-radius: 9px; }}
            QLabel#ImagePreview {{ background-color: {c['cover']}; color: {c['muted']}; border-radius: 9px; }}
            QFrame#VideoPreview {{ background-color: {c['cover']}; border: 1px solid {c['border']}; border-radius: 12px; }}
            QLabel#VideoPlayGlyph {{ color: {accent_hover}; font-size: 40px; font-weight: 800; background: transparent; }}
            QScrollArea {{ border: 1px solid {c['border']}; border-radius: 13px; background-color: {c['window']}; }}
            QScrollArea > QWidget > QWidget {{ background-color: {c['window']}; }}
            QScrollBar:vertical {{ background-color: {c['scroll_bg']}; width: 11px; margin: 4px 2px 4px 2px; border-radius: 5px; }}
            QScrollBar::handle:vertical {{ background-color: {c['scroll_handle']}; min-height: 32px; border-radius: 5px; }}
            QScrollBar::handle:vertical:hover {{ background-color: {accent_hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
            QScrollBar:horizontal {{ background-color: {c['scroll_bg']}; height: 11px; margin: 2px 4px; border-radius: 5px; }}
            QScrollBar::handle:horizontal {{ background-color: {c['scroll_handle']}; min-width: 32px; border-radius: 5px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; }}
            QTabWidget::pane {{
                border: 1px solid {c['border']}; border-radius: 12px;
                background-color: {c['panel']}; top: -1px; padding: 8px;
            }}
            QTabBar::tab {{
                color: {c['secondary']}; background-color: {c['tab']};
                border: 1px solid {c['border']}; border-bottom: none;
                border-top-left-radius: 9px; border-top-right-radius: 9px;
                padding: 9px 15px; margin-right: 4px; min-width: 54px;
            }}
            QTabBar::tab:selected {{ color: {accent_text}; background-color: {c['panel']}; border-color: {accent_hex}; }}
            QTabBar::tab:hover:!selected {{ background-color: {c['button_hover']}; }}
            QCheckBox {{ spacing: 9px; color: {c['text']}; background-color: transparent; padding: 4px 1px; }}
            QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px; border: 1px solid {c['border_strong']}; background-color: {c['input']}; }}
            QCheckBox::indicator:hover {{ border-color: {accent_hover}; }}
            QCheckBox::indicator:checked {{ background-color: {accent_hex}; border: 1px solid {accent_hex}; }}
            QDialogButtonBox {{ background-color: transparent; }}
            QMessageBox QLabel {{ color: {c['text']}; background-color: transparent; font-size: 13px; min-width: 260px; }}
            QMessageBox QPushButton {{ min-width: 82px; }}
            QDialog#ConfirmDialog {{
                background-color: {c['dialog']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 12px;
            }}
            QDialog#ConfirmDialog QWidget {{
                color: {c['text']}; background-color: transparent;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
            }}
            QLabel#ConfirmTitle {{
                color: {c['text']}; background-color: transparent;
                font-size: 16px; font-weight: 700; margin: 0; padding: 0;
            }}
            QLabel#ConfirmQuestion {{
                color: {c['text']}; background-color: transparent;
                font-size: 14px; font-weight: 600; margin: 0; padding: 0;
            }}
            QLabel#ConfirmDetail {{
                color: {c['secondary']}; background-color: transparent;
                font-size: 13px; margin: 0; padding: 0;
            }}
            QPushButton#ConfirmDangerButton {{
                color: #ffffff; background-color: #b42318; border: 1px solid #b42318;
                border-radius: 8px; padding: 8px 14px; min-height: 18px; font-weight: 700;
            }}
            QPushButton#ConfirmDangerButton:hover {{ background-color: #912018; border-color: #912018; }}
            QPushButton#ConfirmCancelButton {{
                color: {c['text']}; background-color: {c['input']};
                border: 1px solid {c['border_strong']}; border-radius: 8px;
                padding: 8px 14px; min-height: 18px; font-weight: 600;
            }}
            QPushButton#ConfirmCancelButton:hover {{ background-color: {c['button_hover']}; }}
            QPushButton#ConfirmCancelButton:focus {{ border: 1px solid {accent_hover}; }}
            QToolTip {{
                color: {c['text']}; background-color: {c['tooltip']};
                border: 1px solid {c['border_strong']}; border-radius: 7px; padding: 6px 8px;
            }}
            QMenu {{ background-color: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px; }}
            QMenu::item {{ border-radius: 5px; padding: 7px 22px; }}
            QMenu::item:selected {{ background-color: {c['nav_active']}; color: {c['text']}; }}
            QFrame#SettingsCard {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
            QFrame#Toast {{
                background-color: {c['card']}; color: {c['text']};
                border: 1px solid {c['border_strong']}; border-radius: 14px;
            }}
            QLabel#ToastIcon {{
                color: #ffffff; background-color: {accent_hex}; border-radius: 12px;
                min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px;
                font-weight: 800; qproperty-alignment: AlignCenter;
            }}
            QLabel#ToastTitle {{ color: {c['text']}; font-size: 13px; font-weight: 750; background: transparent; }}
            QLabel#ToastMessage {{ color: {c['secondary']}; font-size: 11px; background: transparent; }}

            /* Tutler UI polish: calmer surfaces, consistent focus states and cleaner tables/lists. */
            QToolButton {{ color: {c['text']}; background: {c['button']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 6px 9px; }}
            QToolButton:hover {{ background: {c['button_hover']}; border-color: {accent_hover}; }}
            QListWidget, QTreeWidget, QTableWidget {{
                background: {c['card']}; alternate-background-color: {c['panel']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 10px; outline: 0;
                selection-background-color: {c['nav_active']}; selection-color: {c['text']};
                padding: 4px;
            }}
            QListWidget::item, QTreeWidget::item, QTableWidget::item {{ padding: 6px; border-radius: 5px; }}
            QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['button_hover']}; }}
            QHeaderView::section {{ background: {c['sidebar']}; color: {c['secondary']}; border: none; border-bottom: 1px solid {c['border']}; padding: 8px; font-weight: 700; }}
            QGroupBox {{ border: 1px solid {c['border']}; border-radius: 10px; margin-top: 12px; padding: 12px 8px 8px 8px; font-weight: 700; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {c['secondary']}; }}
            QSplitter::handle {{ background: {c['border']}; }}
            QStatusBar {{ background: {c['sidebar']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
            QProgressBar {{ background: {c['border']}; color: {c['text']}; border: none; border-radius: 5px; text-align: center; min-height: 10px; }}
            QProgressBar::chunk {{ background: {accent_hex}; border-radius: 5px; }}

            /* Modern Tutler visual refresh: softer hierarchy, less boxed-in UI. */
            QWidget {{ font-size: 13px; }}
            QWidget#Central {{ background: {c['window']}; }}
            QFrame#Sidebar {{
                background: {c['sidebar']}; border-right: 1px solid {c['border']};
            }}
            QLabel#Brand {{ font-size: 22px; font-weight: 800; letter-spacing: -0.4px; }}
            QLabel#BrandSub {{ font-size: 9px; letter-spacing: 1.2px; }}
            QLabel#PageTitle {{ font-size: 30px; font-weight: 800; letter-spacing: -0.6px; }}
            QLabel#Muted {{ font-size: 12px; }}
            QLabel#ResultsCount {{
                background: {c['nav_active']}; color: {c['text']}; border-radius: 8px;
                padding: 7px 11px; font-size: 12px; font-weight: 750;
            }}
            QPushButton#NavButton {{
                text-align: left; padding: 11px 13px; border: 1px solid transparent;
                background: transparent; color: {c['secondary']}; border-radius: 11px;
                min-height: 20px; font-weight: 550;
            }}
            QPushButton#NavButton:hover {{
                background: {c['nav_hover']}; color: {c['text']}; border-color: {c['border']};
            }}
            QPushButton#NavButton:checked {{
                background: {c['nav_active']}; color: {accent_text}; font-weight: 750;
                border: 1px solid {accent_hex}; padding-left: 13px;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                border: 1px solid {c['border']}; border-radius: 12px;
                padding: 11px 13px; min-height: 20px;
            }}
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
                border: 1px solid {accent_hex}; background: {c['card']};
            }}
            QPushButton {{
                border: 1px solid {c['border']}; border-radius: 11px;
                padding: 10px 15px; min-height: 20px; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {accent_hex}; }}
            QPushButton#PrimaryButton {{
                border-radius: 11px; padding: 11px 17px; font-weight: 750;
            }}
            QFrame#GameCard {{
                background: {c['card']}; border: 1px solid {c['border']}; border-radius: 18px;
            }}
            QFrame#GameCard:hover {{
                background: {c['panel']}; border: 1px solid {accent_hex};
            }}
            QFrame#CoverBox, QLabel#CoverImage, QLabel#CoverPlaceholder {{ border-radius: 12px; }}
            QLabel#CardTitle {{ font-size: 15px; font-weight: 750; }}
            QLabel#PathLabel {{ font-size: 10px; color: {c['subtle']}; }}
            QPushButton#FavoriteButton {{
                min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
                border-radius: 10px; font-size: 18px;
            }}
            QScrollArea#GameScroll {{ border: none; background: transparent; }}
            QScrollArea#GameScroll > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ width: 9px; margin: 2px; background: transparent; }}
            QScrollBar::handle:vertical {{ min-height: 36px; border-radius: 4px; }}
            QMenu {{ border-radius: 11px; padding: 6px; }}
            QToolTip {{ border-radius: 8px; padding: 7px 9px; }}
            QWidget#WindowShell {{ background: {c['window']}; border: 1px solid {c['border']}; border-radius: 14px; }}
            QWidget#Central {{ border-bottom-left-radius: 13px; border-bottom-right-radius: 13px; }}
            QWidget#ModernTitleBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; border-top-left-radius: 13px; border-top-right-radius: 13px; }}
            QLabel#TitleBarLogo {{ background: {accent_hex}; color: white; border-radius: 7px; font-weight: 800; }}
            QLabel#TitleBarName {{ color: {c['text']}; font-size: 13px; font-weight: 800; }}
            QLabel#TitleBarSub {{ color: {c['muted']}; font-size: 9px; letter-spacing: 1.2px; padding-left: 3px; }}
            QPushButton#WindowControlButton, QPushButton#WindowCloseButton {{
                background: transparent; border: none; border-radius: 0px;
                min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px;
                margin: 0; padding: 0; color: {c['text']};
            }}
            QPushButton#WindowControlButton:hover {{ background: {c['button_hover']}; }}
            QPushButton#WindowCloseButton:hover {{ background: #e5484d; color: white; }}
            QMenuBar {{ background: {c['panel']}; color: {c['secondary']}; border: none; padding-left: 12px; }}
            QMenuBar::item {{ padding: 6px 10px; border-radius: 6px; background: transparent; }}
            QMenuBar::item:selected {{ background: {c['button_hover']}; color: {c['text']}; }}
        """
        self.setStyleSheet(stylesheet)
        # Refresh existing raster icons after every theme change, so the sidebar
        # stays legible when switching between light and dark modes at runtime.
        for nav_button in self.findChildren(QPushButton):
            glyph = nav_button.property("nav_icon_glyph")
            if glyph:
                nav_button.setIcon(self._make_nav_icon(str(glyph)))
        apply_native_titlebar_theme(self)
        self._style_ai_floating_button()
        if self._assistant_dialog is not None:
            self._assistant_dialog.apply_theme()
        if app is not None:
            for top_level in app.topLevelWidgets():
                if top_level is not self and top_level.isVisible():
                    apply_native_titlebar_theme(top_level)

    def _is_light_theme(self):
        mode = getattr(self, "theme_mode", "system")
        if mode == "light":
            return True
        if mode == "dark":
            return False
        try:
            scheme = QApplication.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return True
            if scheme == Qt.ColorScheme.Dark:
                return False
        except (AttributeError, TypeError):
            pass
        return QApplication.palette().color(QPalette.ColorRole.Window).lightness() >= 128

    def apply_system_theme(self, *_args):
        if getattr(self, "theme_mode", "system") == "system":
            self._set_styles()

    def exit_application(self):
        self._force_quit = True
        self.close()

    def nativeEvent(self, eventType, message):
        # Frameless 窗口仍保留 Windows 原生边缘拖拽缩放手感。
        if sys.platform == "win32" and not self.isMaximized():
            try:
                import ctypes
                from ctypes import wintypes
                class MSG(ctypes.Structure):
                    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]
                msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
                if msg.message == 0x0084:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    frame = self.frameGeometry()
                    border = 7
                    left = x < frame.left() + border
                    right = x >= frame.right() - border
                    top = y < frame.top() + border
                    bottom = y >= frame.bottom() - border
                    hit = None
                    if top and left: hit = 13  # HTTOPLEFT
                    elif top and right: hit = 14  # HTTOPRIGHT
                    elif bottom and left: hit = 16  # HTBOTTOMLEFT
                    elif bottom and right: hit = 17  # HTBOTTOMRIGHT
                    elif left: hit = 10  # HTLEFT
                    elif right: hit = 11  # HTRIGHT
                    elif top: hit = 12  # HTTOP
                    elif bottom: hit = 15  # HTBOTTOM
                    if hit is not None:
                        return True, hit
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        if getattr(self, "_force_quit", False):
            self._save_active_playtime()
            event.accept()
            return
        behavior = self.settings.value("close_behavior", "ask", type=str)
        if behavior == "minimize":
            event.ignore()
            self.showMinimized()
            return
        if behavior == "ask":
            box = QMessageBox(self)
            box.setWindowTitle(_tr("关闭 Tutler"))
            box.setText(_tr("你希望如何处理 Tutler？"))
            minimize_btn = box.addButton(_tr("最小化"), QMessageBox.ButtonRole.ActionRole)
            quit_btn = box.addButton(_tr("关闭程序"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton(_tr("取消"), QMessageBox.ButtonRole.RejectRole)
            # 三个按钮使用完全一致的尺寸、字体和内边距；仅退出按钮改变颜色，
            # 避免单独设置 padding 后导致按钮高度/基线与其余按钮不齐。
            # Give every action the same fixed geometry so the red destructive
            # action cannot sit higher/lower due to native style or text metrics.
            for action_button in (minimize_btn, quit_btn, cancel_btn):
                action_button.setFixedSize(112, 38)
                action_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            box.setStyleSheet(box.styleSheet() + """
                QMessageBox QPushButton {
                    min-width: 112px;
                    max-width: 112px;
                    min-height: 38px;
                    max-height: 38px;
                    padding: 0px 10px;
                    border-radius: 8px;
                    font-weight: 600;
                    text-align: center;
                }
                QMessageBox QPushButton#CloseProgramButton {
                    color: #ffffff;
                    background-color: #c62828;
                    border: 1px solid #c62828;
                    font-weight: 700;
                }
                QMessageBox QPushButton#CloseProgramButton:hover {
                    background-color: #a61f1f;
                    border-color: #a61f1f;
                }
                QMessageBox QPushButton#CloseProgramButton:pressed {
                    background-color: #861919;
                    border-color: #861919;
                }
            """)
            quit_btn.setObjectName("CloseProgramButton")
            # Explicit per-button styling guarantees a red background even if a
            # platform-native QMessageBox stylesheet has higher precedence.
            quit_btn.setStyleSheet("""
                QPushButton#CloseProgramButton {
                    color: #ffffff;
                    background-color: #c62828;
                    border: 1px solid #c62828;
                    border-radius: 8px;
                    font-weight: 700;
                }
                QPushButton#CloseProgramButton:hover {
                    background-color: #a61f1f;
                    border-color: #a61f1f;
                }
                QPushButton#CloseProgramButton:pressed {
                    background-color: #861919;
                    border-color: #861919;
                }
            """)
            box.setDefaultButton(minimize_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked == minimize_btn:
                event.ignore()
                self.showMinimized()
                return
            if clicked != quit_btn:
                event.ignore()
                return
        self._save_active_playtime()
        event.accept()

    def _save_active_playtime(self):
        active = getattr(self, "_active_play", None)
        if not active or psutil is None:
            return
        elapsed = max(0, int(min(time.monotonic(), active.get("last_seen", time.monotonic())) - active.get("started", time.monotonic())))
        if elapsed > 0:
            with db_connect() as conn:
                conn.execute("UPDATE games SET playtime_seconds=playtime_seconds+? WHERE id=?", (elapsed, active["game_id"]))
        self._active_play = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "cards_grid"):
            self.refresh_games()
        if getattr(self, "_progress_toasts", None):
            self._position_progress_toasts()
        self._position_ai_floating_button()
        assistant_dialog = getattr(self, "_assistant_dialog", None)
        if assistant_dialog is not None and assistant_dialog.isVisible():
            assistant_dialog.position_near_button(self.assistant_button)

    def show_toast(self, title, message="", duration=3600):
        """Show a short in-app notification without a native title bar or modal popup."""
        old_toast = getattr(self, "_toast_widget", None)
        if old_toast is not None:
            try:
                old_toast.hide()
                old_toast.deleteLater()
            except RuntimeError:
                pass

        toast = QFrame(self)
        toast.setObjectName("Toast")
        toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(toast)
        row.setContentsMargins(14, 11, 16, 11)
        row.setSpacing(11)
        icon_label = QLabel("✓")
        icon_label.setObjectName("ToastIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)
        title_label = QLabel(title)
        title_label.setObjectName("ToastTitle")
        text_column.addWidget(title_label)
        if message:
            message_label = QLabel(message)
            message_label.setObjectName("ToastMessage")
            message_label.setWordWrap(True)
            message_label.setMaximumWidth(390)
            text_column.addWidget(message_label)
        row.addLayout(text_column, 1)

        toast.setMaximumWidth(470)
        toast.adjustSize()
        toast_width = min(470, max(290, toast.sizeHint().width()))
        toast.resize(toast_width, toast.sizeHint().height())
        scan_stack_height = sum(
            data["widget"].height() + 10 for data in getattr(self, "_progress_toasts", {}).values()
            if data.get("widget") is not None and data["widget"].isVisible()
        )
        toast.move(max(18, self.width() - toast.width() - 24),
                   max(18, self.height() - toast.height() - 28 - scan_stack_height))
        toast.show()
        toast.raise_()
        self._toast_widget = toast
        QTimer.singleShot(duration, toast.hide)

    def open_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Tutler 应用设置")
        dlg.setMinimumSize(560, 430)
        outer = QVBoxLayout(dlg)
        tabs = QTabWidget(dlg)
        outer.addWidget(tabs, 1)

        # UI tab
        ui_tab = QWidget()
        ui_layout = QVBoxLayout(ui_tab)
        language_label = QLabel("界面语言")
        language_combo = QComboBox()
        language_combo.addItem("简体中文", "zh_CN")
        language_combo.addItem("English", "en_US")
        current_language = self.settings.value("language", "zh_CN", type=str)
        language_index = language_combo.findData(current_language)
        language_combo.setCurrentIndex(language_index if language_index >= 0 else 0)
        ui_layout.addWidget(language_label)
        ui_layout.addWidget(language_combo)
        language_hint = QLabel("语言更改后需要重启应用才能生效。")
        language_hint.setWordWrap(True)
        language_hint.setObjectName("Hint")
        ui_layout.addWidget(language_hint)
        theme_label = QLabel("应用主题")
        theme_combo = QComboBox()
        theme_combo.addItem("跟随系统", "system")
        theme_combo.addItem("深色", "dark")
        theme_combo.addItem("亮色", "light")
        current_theme = self.settings.value("theme_mode", "system", type=str)
        idx = theme_combo.findData(current_theme)
        theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        ui_layout.addWidget(theme_label)
        ui_layout.addWidget(theme_combo)
        auto_covers = QCheckBox("识别 Steam 时自动下载游戏封面（需要网络）")
        auto_covers.setChecked(self.settings.value("auto_download_covers", True, type=bool))
        auto_scan = QCheckBox("启动应用时自动识别 Steam 游戏")
        auto_scan.setChecked(self.settings.value("auto_scan_steam", False, type=bool))
        track_playtime = QCheckBox("统计游戏运行时长（需要安装 psutil）")
        track_playtime.setChecked(self.settings.value("track_playtime", True, type=bool))
        ui_layout.addSpacing(10)
        ui_layout.addWidget(auto_covers)
        ui_layout.addWidget(auto_scan)
        ui_layout.addWidget(track_playtime)
        ui_layout.addStretch(1)
        tabs.addTab(ui_tab, "界面")

        # Steam tab
        steam_tab = QWidget()
        steam_layout = QVBoxLayout(steam_tab)
        steam_layout.addWidget(QLabel("Steam 安装路径（可选；留空则自动识别）"))
        steam_path = QLineEdit(self.settings.value("steam_path", "", type=str))
        steam_path.setPlaceholderText(r"例如：C:\Program Files (x86)\Steam")
        steam_buttons = QHBoxLayout()
        browse_steam = QPushButton("浏览…")
        auto_detect = QPushButton("自动识别")
        steam_buttons.addWidget(browse_steam)
        steam_buttons.addWidget(auto_detect)
        steam_buttons.addStretch(1)
        steam_layout.addWidget(steam_path)
        steam_layout.addLayout(steam_buttons)
        steam_status = QLabel("路径留空时会搜索常见安装位置和 Windows 注册表。")
        steam_status.setWordWrap(True)
        steam_status.setObjectName("Hint")
        steam_layout.addWidget(steam_status)
        steam_layout.addStretch(1)
        def browse_steam_path():
            path = QFileDialog.getExistingDirectory(dlg, "选择 Steam 安装目录", steam_path.text().strip() or str(Path.home()))
            if path:
                steam_path.setText(path)
        def detect_steam_path():
            roots = steam_roots()
            install = next((p for p in roots if (p / "steam.exe").exists() or (p / "Steam.exe").exists()), None)
            if install is None and roots:
                install = roots[0]
            if install:
                steam_path.setText(str(install))
                steam_status.setText(f"已识别路径：{install}")
            else:
                steam_status.setText("未找到 Steam。请手动选择包含 steam.exe 或 steamapps 文件夹的目录。")
        browse_steam.clicked.connect(browse_steam_path)
        auto_detect.clicked.connect(detect_steam_path)
        tabs.addTab(steam_tab, "Steam")

        # Window behavior tab
        window_tab = QWidget()
        window_layout = QVBoxLayout(window_tab)
        window_layout.addWidget(QLabel("点击窗口右上角关闭按钮时"))
        close_behavior = QComboBox()
        close_behavior.addItem("每次询问（最小化 / 关闭程序 / 取消）", "ask")
        close_behavior.addItem("最小化窗口", "minimize")
        close_behavior.addItem("直接关闭程序", "quit")
        current_behavior = self.settings.value("close_behavior", "ask", type=str)
        close_index = close_behavior.findData(current_behavior)
        close_behavior.setCurrentIndex(close_index if close_index >= 0 else 0)
        window_layout.addWidget(close_behavior)
        window_hint = QLabel("选择“最小化窗口”后，点击关闭按钮会将窗口最小化到任务栏，不会退出进程。")
        window_hint.setWordWrap(True)
        window_hint.setObjectName("Hint")
        window_layout.addWidget(window_hint)
        confirm_launch = QCheckBox("启动游戏前显示确认提示")
        confirm_launch.setChecked(self.settings.value("confirm_launch", False, type=bool))
        window_layout.addWidget(confirm_launch)
        window_layout.addStretch(1)
        tabs.addTab(window_tab, "窗口")

        # About tab
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_title = QLabel("Tutler")
        about_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        about_layout.addWidget(about_title)
        about_layout.addWidget(QLabel(f"当前版本：{APP_VERSION}"))
        about_layout.addWidget(QLabel("本地 PC 游戏管理器"))
        about_layout.addSpacing(8)
        data_info = QLabel(f"数据目录：{APP_DIR}\n数据库：{DB_PATH}")
        data_info.setWordWrap(True)
        data_info.setObjectName("Hint")
        about_layout.addWidget(data_info)
        about_layout.addStretch(1)
        tabs.addTab(about_tab, "关于")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        outer.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            old_language = self.settings.value("language", "zh_CN", type=str)
            new_language = language_combo.currentData()
            self.settings.setValue("language", new_language)
            self.settings.setValue("theme_mode", theme_combo.currentData())
            self.settings.setValue("auto_scan_steam", auto_scan.isChecked())
            self.settings.setValue("auto_download_covers", auto_covers.isChecked())
            self.settings.setValue("track_playtime", track_playtime.isChecked())
            self.settings.setValue("confirm_launch", confirm_launch.isChecked())
            self.settings.setValue("steam_path", steam_path.text().strip())
            self.settings.setValue("close_behavior", close_behavior.currentData())
            self.settings.sync()
            self.theme_mode = self.settings.value("theme_mode", "system", type=str)
            self._set_styles()
            if old_language != new_language:
                self.show_toast(
                    "语言设置已保存",
                    "语言将在重新启动 Tutler 后生效。" if new_language == "zh_CN" else
                    "Language preference saved. Restart Tutler to apply it.",
                    duration=5200,
                )
            else:
                self.show_toast(
                    "设置已保存",
                    "主题立即生效；Steam 路径将在下次扫描时使用，启动时自动识别将在下次启动时执行。"
                )

    def show_about(self):
        QMessageBox.about(
            self, "关于 Tutler",
            f"Tutler {APP_VERSION}\n本地 PC 游戏、视频与图片管理器\n\n数据库：\n{DB_PATH}\n\n游戏文件不会被复制、移动或删除。"
        )

    def change_view(self, view):
        self.current_view = view
        self.current_category = view.split(":", 1)[1] if view.startswith("category:") else ""
        is_videos = view == "videos" or view.startswith("video_category:")
        is_images = view == "images" or view.startswith("image_category:")
        self.current_video_category = view.split(":", 1)[1] if view.startswith("video_category:") else ""
        self.current_image_category = view.split(":", 1)[1] if view.startswith("image_category:") else ""
        is_media = is_videos or is_images
        is_game_category = view.startswith("category:")

        # Keep the page's actual navigation item selected when entering a library's
        # default page, including clicks on library headers and reset-to-all actions.
        target_button = None
        if view == "all":
            target_button = self.all_btn
        elif view == "favorites":
            target_button = self.fav_btn
        elif view == "recent":
            target_button = getattr(self, "recent_btn", None)
        elif view == "videos":
            target_button = self.video_btn
        elif view == "images":
            target_button = self.image_btn
        elif view.startswith("category:"):
            target_button = self.category_nav_buttons.get(self.current_category)
        elif view.startswith("video_category:"):
            target_button = self.video_category_nav_buttons.get(self.current_video_category)
        elif view.startswith("image_category:"):
            target_button = self.image_category_nav_buttons.get(self.current_image_category)
        if target_button is not None and not target_button.isChecked():
            target_button.setChecked(True)

        # 页面导航与侧栏展开状态分离：切换“全部游戏/我的收藏/具体分类”时，
        # 保持游戏库及分类列表的展开状态；进入视频或图片页面时切换到对应资源库。
        # 分类列表在切走媒体库时保留 checked 状态，返回游戏库后自动恢复显示。
        if is_videos:
            self._activate_library_section("video")
        elif is_images:
            self._activate_library_section("image")
        elif is_game_category:
            self._activate_library_section("game")
            self._set_category_section_expanded(True)
        else:
            # 游戏主页面也应位于游戏库中，但不要因导航而收起分类列表。
            self._activate_library_section("game")
        self.add_btn.setVisible(not is_media)
        self.scan_btn.setVisible(not is_media)
        self.steam_btn.setVisible(not is_media)
        self.video_scan_btn.setVisible(is_videos)
        self.image_scan_btn.setVisible(is_images)
        self.sort_box.setVisible(not is_media)
        self.import_btn.setVisible(not is_media)
        self.export_btn.setVisible(not is_media)
        if is_videos:
            self.page_title.setText(self.current_video_category or "全部视频")
            self.page_subtitle.setText("浏览本机视频文件，点击后使用 Windows 默认视频播放器打开")
            self.search_edit.setPlaceholderText("搜索视频名称或文件路径…")
        elif is_images:
            self.page_title.setText(self.current_image_category or "全部图片")
            self.page_subtitle.setText("浏览本机图片文件，点击后使用 Windows 默认图片查看器打开")
            self.search_edit.setPlaceholderText("搜索图片名称或文件路径…")
        elif view == "all":
            self.page_title.setText("全部游戏")
            self.page_subtitle.setText("管理并启动你电脑上的游戏")
            self.search_edit.setPlaceholderText("⌕   搜索游戏名称、路径或标签…")
        elif view == "favorites":
            self.page_title.setText("我的收藏")
            self.page_subtitle.setText("快速访问你最喜欢的游戏")
            self.search_edit.setPlaceholderText("⌕   搜索游戏名称、路径或标签…")
        elif view == "recent":
            self.page_title.setText("最近游玩")
            self.page_subtitle.setText("查看最近启动过的游戏")
            self.search_edit.setPlaceholderText("⌕   搜索游戏名称、路径或标签…")
        else:
            self.page_title.setText(self.current_category)
            self.page_subtitle.setText(f"分类：{self.current_category}")
            self.search_edit.setPlaceholderText("⌕   搜索游戏名称、路径或标签…")
        self.refresh_games()

    def query_games(self):
        # Apply library/category constraints in SQL, then rank search results in Python.
        # This permits partial words and small spelling mistakes instead of SQL LIKE only.
        sql = "SELECT * FROM games WHERE 1=1"
        params = []
        if self.current_view == "favorites":
            sql += " AND favorite=1"
        elif self.current_view == "recent":
            sql += " AND COALESCE(last_played, '') <> ''"
        elif self.current_view.startswith("category:"):
            sql += " AND category=?"
            params.append(self.current_category)

        sort = self.sort_box.currentText()
        if self.current_view == "recent" or sort == "最近游玩":
            sql += " ORDER BY last_played DESC, name COLLATE NOCASE"
        elif sort == "名称 A-Z":
            sql += " ORDER BY name COLLATE NOCASE ASC"
        elif sort == "启动次数":
            sql += " ORDER BY play_count DESC, name COLLATE NOCASE"
        else:
            sql += " ORDER BY id DESC"

        with db_connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        query = self.search_edit.text().strip()
        if not query:
            return rows

        ranked = []
        for row in rows:
            score = _fuzzy_search_score(
                query,
                row["name"],
                row["exe_path"],
                row["tags"],
            )
            if score > 0:
                ranked.append((score, row))
        # Keep the user's selected sort as the tie-breaker, only improving relevance.
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in ranked]

    def refresh_games(self, *_):
        if self.current_view == "videos" or self.current_view.startswith("video_category:"):
            self.refresh_videos()
            return
        if self.current_view == "images" or self.current_view.startswith("image_category:"):
            self.refresh_images()
            return
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        games = self.query_games()
        available_width = max(600, self.scroll.viewport().width())
        columns = max(1, min(5, available_width // 300))
        for index, game in enumerate(games):
            card = GameCard(game)
            card.launch_requested.connect(self.launch_game)
            card.edit_requested.connect(self.edit_game)
            card.delete_requested.connect(self.delete_game)
            card.favorite_requested.connect(self.set_favorite)
            self.cards_grid.addWidget(card, index // columns, index % columns)

        for col in range(columns):
            self.cards_grid.setColumnStretch(col, 1)
        self.count_label.setText(f"{len(games)} 款游戏")
        self.status_label.setText("本机离线库")
        if not games:
            empty = QLabel("这里暂时没有游戏\n\n点击「添加游戏」或「扫描目录」开始建立你的游戏库。")
            empty.setObjectName("EmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(240)
            empty.setStyleSheet("color:#7f899d; font-size:15px;")
            self.cards_grid.addWidget(empty, 0, 0, 1, columns)

    def _position_progress_toasts(self):
        """Stack independent scan notifications so concurrent scans never overwrite one another."""
        bottom = self.height() - 24
        for key, data in reversed(list(self._progress_toasts.items())):
            toast = data.get("widget")
            if toast is None:
                continue
            toast.adjustSize()
            width = min(470, max(300, toast.sizeHint().width()))
            toast.resize(width, toast.sizeHint().height())
            bottom -= toast.height()
            toast.move(max(18, self.width() - toast.width() - 24), max(18, bottom))
            toast.raise_()
            bottom -= 10

    def _show_scan_progress(self, key, title, message, finished=False, failed=False):
        data = self._progress_toasts.get(key)
        if data is None:
            toast = QFrame(self)
            toast.setObjectName("Toast")
            row = QHBoxLayout(toast)
            row.setContentsMargins(14, 10, 16, 10)
            row.setSpacing(10)
            icon = QLabel("!" if failed else "✓" if finished else "↻")
            icon.setObjectName("ToastIcon")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            title_label = QLabel(title)
            title_label.setObjectName("ToastTitle")
            message_label = QLabel(message)
            message_label.setObjectName("ToastMessage")
            message_label.setWordWrap(True)
            message_label.setMaximumWidth(390)
            progress = QProgressBar()
            progress.setObjectName("ScanProgress")
            progress.setRange(0, 0)
            progress.setTextVisible(False)
            progress.setMaximumHeight(5)
            col.addWidget(title_label)
            col.addWidget(message_label)
            col.addWidget(progress)
            row.addLayout(col, 1)
            toast.setMaximumWidth(470)
            data = {"widget": toast, "icon": icon, "title": title_label, "message": message_label, "progress": progress}
            self._progress_toasts[key] = data
        data["title"].setText(title)
        data["message"].setText(message)
        data["icon"].setText("!" if failed else "✓" if finished else "↻")
        data["progress"].setVisible(not finished and not failed)
        self._position_progress_toasts()
        data["widget"].show()
        if finished or failed:
            QTimer.singleShot(4500, lambda k=key: self._remove_scan_progress(k))

    def _remove_scan_progress(self, key):
        data = self._progress_toasts.pop(key, None)
        if data:
            data["widget"].hide()
            data["widget"].deleteLater()
            self._position_progress_toasts()

    def add_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择视频目录", str(Path.home()))
        if not folder:
            return
        roots = list(self.settings.value("video_roots", [], type=list))
        normalized = normalized_path(folder)
        target_category = self.current_video_category if self.current_view.startswith("video_category:") else ""
        self._pending_video_category_assignment = (normalized, target_category) if target_category else None
        if normalized not in {normalized_path(item) for item in roots if item}:
            roots.append(normalized)
            self.settings.setValue("video_roots", roots)
            self.settings.sync()
        self.scan_video_folders()

    def scan_video_folders(self):
        if self.video_worker is not None:
            return
        roots = list(self.settings.value("video_roots", [], type=list))
        roots = [root for root in roots if os.path.isdir(root)]
        if not roots:
            self.add_video_folder()
            return
        self.video_scan_btn.setEnabled(False)
        self.status_label.setText("正在扫描视频目录…")
        self._show_scan_progress("video", "正在扫描视频目录", f"正在检查 {len(roots)} 个目录…")
        self.video_worker = VideoScanWorker(roots, self)
        self.video_worker.progress.connect(lambda message: self._show_scan_progress("video", "正在扫描视频目录", message))
        self.video_worker.found.connect(self.on_videos_found)
        self.video_worker.failed.connect(self.on_video_scan_failed)
        self.video_worker.finished.connect(self.on_video_scan_finished)
        self.video_worker.start()

    def on_videos_found(self, videos):
        self.video_files = list(videos)
        self.video_category_map = {p: c for p, c in self.video_category_map.items() if p in self.video_files}
        assigned_count = 0
        pending = self._pending_video_category_assignment
        self._pending_video_category_assignment = None
        if pending:
            target_root, target_category = pending
            for path in self.video_files:
                try:
                    inside = os.path.commonpath([normalized_path(path), target_root]) == target_root
                except (ValueError, OSError):
                    inside = False
                if inside:
                    self.video_category_map[path] = target_category
                    assigned_count += 1
        self.settings.setValue("video_files", self.video_files)
        self.settings.setValue("video_category_map", self.video_category_map)
        self.settings.sync()
        self.refresh_videos()
        self.status_label.setText(f"已找到 {len(videos)} 个视频文件")
        detail = f"共找到 {len(videos)} 个视频文件。"
        if assigned_count:
            detail += f"其中 {assigned_count} 个已归入分类「{pending[1]}」。"
        self._show_scan_progress("video", "视频扫描完成", detail, finished=True)

    def on_video_scan_failed(self, message):
        self._pending_video_category_assignment = None
        self._show_scan_progress("video", "视频扫描失败", message, failed=True)

    def on_video_scan_finished(self):
        self.video_worker = None
        self.video_scan_btn.setEnabled(True)

    def _backfill_missing_covers(self):
        """为库中尚无封面、且 EXE 仍然存在的游戏批量提取 EXE 图标作为封面。"""
        with db_connect() as conn:
            rows = conn.execute(
                "SELECT id, exe_path FROM games WHERE COALESCE(cover_path, '') = ''"
            ).fetchall()
        changed = 0
        for row in rows:
            exe = row["exe_path"]
            if exe.lower().startswith("steam://") or not os.path.isfile(exe):
                continue
            cover = extract_exe_icon_as_cover(exe)
            if cover:
                with db_connect() as conn:
                    conn.execute("UPDATE games SET cover_path=? WHERE id=?", (cover, row["id"]))
                changed += 1
        if changed:
            self.refresh_games()
            self.show_toast("封面已补全", f"已为 {changed} 款游戏提取 EXE 图标作为封面。")

    def refresh_videos(self):
        # Generate missing video frames in a worker so opening/searching the video
        # library never blocks the UI. Cached frames are reused on later visits.
        if self.video_thumbnail_worker is None and shutil.which("ffmpeg"):
            missing = [p for p in self.video_files if os.path.isfile(p) and not video_thumbnail_path(p).is_file()]
            if missing:
                self.video_thumbnail_worker = VideoThumbnailWorker(missing, self)
                self.video_thumbnail_worker.finished.connect(self._on_video_thumbnails_ready)
                self.video_thumbnail_worker.start()
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        query = self.search_edit.text().strip().casefold()
        videos = [p for p in self.video_files if os.path.isfile(p)
                  and (not self.current_view.startswith("video_category:") or self.video_category_map.get(p, "") == self.current_video_category)
                  and (not query or _fuzzy_search_score(query, Path(p).name, p) > 0)]
        available_width = max(600, self.scroll.viewport().width())
        columns = max(1, min(5, available_width // 300))
        for index, video_path in enumerate(videos):
            card = VideoCard(video_path, self._ordered_video_categories(), self.video_category_map.get(video_path, ""))
            card.play_requested.connect(self.play_video)
            card.category_changed.connect(self.set_video_category)
            card.remove_requested.connect(self.remove_video_from_library)
            self.cards_grid.addWidget(card, index // columns, index % columns)
        for col in range(columns):
            self.cards_grid.setColumnStretch(col, 1)
        self.count_label.setText(f"{len(videos)} 个视频")
        self.status_label.setText(f"视频目录：{len(self.settings.value('video_roots', [], type=list))} 个")
        if not videos:
            empty = QLabel("还没有视频资源\n\n点击「添加视频目录」，选择包含视频的文件夹开始扫描。\n视频库默认没有分类；可使用左侧「自定义视频分类」创建自己的分类。\n支持 MP4、MKV、AVI、MOV、WMV、WebM 等常见格式。")
            empty.setObjectName("EmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(240)
            empty.setWordWrap(True)
            self.cards_grid.addWidget(empty, 0, 0, 1, columns)

    def _on_video_thumbnails_ready(self):
        worker = self.video_thumbnail_worker
        generated_count = worker.generated_count if worker is not None else 0
        self.video_thumbnail_worker = None
        if self.current_view == "videos" or self.current_view.startswith("video_category:"):
            self.refresh_videos()
        if generated_count:
            self.status_label.setText(f"已生成 {generated_count} 张视频封面")

    def add_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片目录", str(Path.home()))
        if not folder:
            return
        roots = list(self.settings.value("image_roots", [], type=list))
        normalized = normalized_path(folder)
        target_category = self.current_image_category if self.current_view.startswith("image_category:") else ""
        self._pending_image_category_assignment = (normalized, target_category) if target_category else None
        if normalized not in {normalized_path(item) for item in roots if item}:
            roots.append(normalized)
            self.settings.setValue("image_roots", roots)
            self.settings.sync()
        self.scan_image_folders()

    def scan_image_folders(self):
        if self.image_worker is not None:
            return
        roots = [root for root in self.settings.value("image_roots", [], type=list) if os.path.isdir(root)]
        if not roots:
            self.add_image_folder()
            return
        self.image_scan_btn.setEnabled(False)
        self.status_label.setText("正在扫描图片目录…")
        self._show_scan_progress("image", "正在扫描图片目录", f"正在检查 {len(roots)} 个目录…")
        self.image_worker = ImageScanWorker(roots, self)
        self.image_worker.progress.connect(lambda message: self._show_scan_progress("image", "正在扫描图片目录", message))
        self.image_worker.found.connect(self.on_images_found)
        self.image_worker.failed.connect(self.on_image_scan_failed)
        self.image_worker.finished.connect(self.on_image_scan_finished)
        self.image_worker.start()

    def on_images_found(self, images):
        self.image_files = list(images)
        self.image_category_map = {p: c for p, c in self.image_category_map.items() if p in self.image_files}
        assigned_count = 0
        pending = self._pending_image_category_assignment
        self._pending_image_category_assignment = None
        if pending:
            target_root, target_category = pending
            for path in self.image_files:
                try:
                    inside = os.path.commonpath([normalized_path(path), target_root]) == target_root
                except (ValueError, OSError):
                    inside = False
                if inside:
                    self.image_category_map[path] = target_category
                    assigned_count += 1
        self.settings.setValue("image_files", self.image_files)
        self.settings.setValue("image_category_map", self.image_category_map)
        self.settings.sync()
        self.refresh_images()
        self.status_label.setText(f"已找到 {len(images)} 张图片")
        detail = f"共找到 {len(images)} 张图片。"
        if assigned_count:
            detail += f"其中 {assigned_count} 张已归入分类「{pending[1]}」。"
        self._show_scan_progress("image", "图片扫描完成", detail, finished=True)

    def on_image_scan_failed(self, message):
        self._pending_image_category_assignment = None
        self._show_scan_progress("image", "图片扫描失败", message, failed=True)

    def on_image_scan_finished(self):
        self.image_worker = None
        self.image_scan_btn.setEnabled(True)

    def refresh_images(self):
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        query = self.search_edit.text().strip().casefold()
        images = [p for p in self.image_files if os.path.isfile(p)
                  and (not self.current_view.startswith("image_category:") or self.image_category_map.get(p, "") == self.current_image_category)
                  and (not query or _fuzzy_search_score(query, Path(p).name, p) > 0)]
        available_width = max(600, self.scroll.viewport().width())
        columns = max(1, min(5, available_width // 300))
        categories = self._ordered_image_categories()
        for index, image_path in enumerate(images):
            card = ImageCard(image_path, categories, self.image_category_map.get(image_path, ""))
            card.open_requested.connect(self.open_image_file)
            card.category_changed.connect(self.set_image_category)
            card.remove_requested.connect(self.remove_image_from_library)
            self.cards_grid.addWidget(card, index // columns, index % columns)
        for col in range(columns):
            self.cards_grid.setColumnStretch(col, 1)
        self.count_label.setText(f"{len(images)} 张图片")
        self.status_label.setText(f"图片目录：{len(self.settings.value('image_roots', [], type=list))} 个")
        if not images:
            empty = QLabel("还没有图片资源\n\n点击「添加图片目录」，选择包含图片的文件夹开始扫描。\n图片库默认没有分类；可通过左侧「自定义图片分类」创建分类。")
            empty.setObjectName("EmptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(240)
            empty.setWordWrap(True)
            self.cards_grid.addWidget(empty, 0, 0, 1, columns)

    def remove_video_from_library(self, video_path):
        name = Path(video_path).name
        if not self._confirm_action(
            "从视频库移除",
            f"确定从 Tutler 视频库中移除「{name}」吗？",
            "只会移除视频库记录及其分类信息，不会删除硬盘上的视频文件。",
            confirm_text="移除视频",
        ):
            return
        self.video_files = [p for p in self.video_files if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(video_path))]
        self.video_category_map.pop(video_path, None)
        self.settings.setValue("video_files", self.video_files)
        self.settings.setValue("video_category_map", self.video_category_map)
        self.settings.sync()
        self.refresh_videos()
        self.show_toast("已移除视频", f"「{name}」已从视频库移除，原文件未删除。")

    def remove_image_from_library(self, image_path):
        name = Path(image_path).name
        if not self._confirm_action(
            "从图片库移除",
            f"确定从 Tutler 图片库中移除「{name}」吗？",
            "只会移除图片库记录及其分类信息，不会删除硬盘上的图片文件。",
            confirm_text="移除图片",
        ):
            return
        self.image_files = [p for p in self.image_files if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(image_path))]
        self.image_category_map.pop(image_path, None)
        self.settings.setValue("image_files", self.image_files)
        self.settings.setValue("image_category_map", self.image_category_map)
        self.settings.sync()
        self.refresh_images()
        self.show_toast("已移除图片", f"「{name}」已从图片库移除，原文件未删除。")

    def set_image_category(self, image_path, category):
        self.image_category_map[image_path] = category or ""
        self.settings.setValue("image_category_map", self.image_category_map)
        self.settings.sync()
        if self.current_view.startswith("image_category:") and self.current_image_category != category:
            self.refresh_images()

    def open_image_file(self, image_path):
        if not os.path.isfile(image_path):
            QMessageBox.warning(self, "图片不存在", f"找不到图片文件：\n{image_path}\n请重新扫描图片目录。")
            return
        try:
            if sys.platform == "win32":
                os.startfile(image_path)
            else:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(image_path)):
                    raise RuntimeError("系统未能打开此图片文件")
            self.status_label.setText(f"已请求图片查看器打开：{Path(image_path).name}")
        except Exception as exc:
            QMessageBox.warning(self, "无法打开图片", f"无法调用系统默认图片查看器：\n{exc}")

    def set_video_category(self, video_path, category):
        self.video_category_map[video_path] = category or ""
        self.settings.setValue("video_category_map", self.video_category_map)
        self.settings.sync()
        if self.current_view.startswith("video_category:") and self.current_video_category != category:
            self.refresh_videos()

    def play_video(self, video_path):
        if not os.path.isfile(video_path):
            QMessageBox.warning(self, "视频不存在", f"找不到视频文件：\n{video_path}\n请重新扫描视频目录。")
            return
        try:
            # Use the Windows file association so the user's Windows default video player opens it.
            if sys.platform == "win32":
                os.startfile(video_path)
            else:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(video_path)):
                    raise RuntimeError("系统未能打开此视频文件")
            self.status_label.setText(f"已请求播放器打开：{Path(video_path).name}")
        except Exception as exc:
            QMessageBox.warning(self, "无法播放视频", f"无法调用系统默认播放器：\n{exc}")

    def add_game(self):
        dialog = GameDialog(self, categories=self._all_categories())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_game(dialog.values())

    def save_game(self, values, game_id=None):
        try:
            data = dict(values)
            cover_path = data.pop("cover_path", "")
            if (
                not cover_path
                and data.get("exe_path")
                and not data["exe_path"].lower().startswith("steam://")
                and os.path.isfile(data["exe_path"])
            ):
                extracted = extract_exe_icon_as_cover(data["exe_path"])
                if extracted:
                    cover_path = extracted
            if game_id is None:
                with db_connect() as conn:
                    conn.execute("""
                        INSERT INTO games
                        (name, exe_path, launch_args, category, tags, notes, cover_path, steam_appid, install_dir, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["name"], data["exe_path"], data["launch_args"], data["category"],
                        data["tags"], data["notes"], cover_path, data.get("steam_appid", ""), data.get("install_dir", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
            else:
                with db_connect() as conn:
                    conn.execute("""
                        UPDATE games SET name=?, exe_path=?, launch_args=?, category=?, tags=?, notes=?, cover_path=?, steam_appid=?, install_dir=?
                        WHERE id=?
                    """, (
                        data["name"], data["exe_path"], data["launch_args"], data["category"],
                        data["tags"], data["notes"], cover_path, data.get("steam_appid", ""), data.get("install_dir", ""), game_id
                    ))
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "重复路径", "这个 EXE 已经在游戏库中了。每个 EXE 路径只能收录一次。")
            return
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.refresh_games()

    def edit_game(self, game_id):
        with db_connect() as conn:
            game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not game:
            return
        dialog = GameDialog(self, game=game, categories=self._all_categories())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.save_game(dialog.values(), game_id)

    def _confirm_action(self, title, question, detail="", confirm_text="确认"):
        """主题自适应的危险操作确认框。

        Windows 浅色主题下 QMessageBox 的尺寸和配色容易偏移，因此删除类操作
        统一使用这个自绘对话框，与「删除自定义分类」保持一致的视觉与行为。
        """
        dialog = QDialog(self)
        dialog.setObjectName("ConfirmDialog")
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(440)
        dialog.setMaximumWidth(520)
        dialog.setAutoFillBackground(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("ConfirmTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        question_label = QLabel(question)
        question_label.setObjectName("ConfirmQuestion")
        question_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        question_label.setWordWrap(True)
        layout.addWidget(question_label)

        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("ConfirmDetail")
            detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)

        layout.addSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("ConfirmCancelButton")
        cancel_button.setMinimumWidth(92)
        confirm_button = QPushButton(confirm_text)
        confirm_button.setObjectName("ConfirmDangerButton")
        confirm_button.setMinimumWidth(100)
        buttons.addWidget(cancel_button)
        buttons.addWidget(confirm_button)
        layout.addLayout(buttons)

        # 回车默认走“取消”，避免误删。
        cancel_button.setDefault(True)
        cancel_button.clicked.connect(dialog.reject)
        confirm_button.clicked.connect(dialog.accept)

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _show_message(self, title, message):
        """主题自适应的信息 / 错误提示框，视觉风格与 _confirm_action 保持一致。

        用于导入 / 导出等非破坏性操作的结果反馈。复用 ConfirmDialog 的
        objectName，无需额外维护样式；文字可被鼠标选中复制，方便阅读路径类信息。
        """
        dialog = QDialog(self)
        dialog.setObjectName("ConfirmDialog")
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(440)
        dialog.setMaximumWidth(560)
        dialog.setAutoFillBackground(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("ConfirmTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("ConfirmQuestion")
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(message_label)

        layout.addSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        ok_button = QPushButton("知道了")
        ok_button.setObjectName("ConfirmCancelButton")
        ok_button.setMinimumWidth(96)
        buttons.addWidget(ok_button)
        layout.addLayout(buttons)

        ok_button.setDefault(True)
        ok_button.clicked.connect(dialog.accept)
        dialog.exec()

    def delete_game(self, game_id):
        with db_connect() as conn:
            game = conn.execute("SELECT name FROM games WHERE id=?", (game_id,)).fetchone()
        if not game:
            return
        if self._confirm_action(
            "移除游戏",
            f"确定从 Tutler 中移除「{game['name']}」吗？",
            "只会删除游戏库记录和启动历史，不会删除游戏文件。",
            confirm_text="移除游戏",
        ):
            with db_connect() as conn:
                conn.execute("DELETE FROM games WHERE id=?", (game_id,))
            self.refresh_games()

    def set_favorite(self, game_id, favorite):
        with db_connect() as conn:
            conn.execute("UPDATE games SET favorite=? WHERE id=?", (int(favorite), game_id))
        self.refresh_games()

    def launch_game(self, game_id):
        with db_connect() as conn:
            game = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not game:
            return False
        path = game["exe_path"]
        is_steam = bool(game["steam_appid"] or path.lower().startswith("steam://rungameid/"))
        if not is_steam and not os.path.isfile(path):
            QMessageBox.warning(self, "找不到游戏", f"文件不存在：\n{path}\n\n如果游戏移动了位置，请编辑游戏并更新路径。")
            return False
        if self.settings.value("confirm_launch", False, type=bool):
            answer = QMessageBox.question(
                self, "启动游戏", f"确定启动「{game['name']}」吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        try:
            args = shlex.split(game["launch_args"] or "", posix=False)
            if is_steam:
                appid = game["steam_appid"] or path.rsplit("/", 1)[-1]
                if not appid:
                    raise ValueError("缺少 Steam AppID")
                os.startfile(f"steam://rungameid/{appid}")
            else:
                subprocess.Popen([path, *args], cwd=os.path.dirname(path) or None, shell=False)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with db_connect() as conn:
                conn.execute("UPDATE games SET play_count=play_count+1, last_played=? WHERE id=?", (now, game_id))
                conn.execute("INSERT INTO play_history(game_id, launched_at) VALUES (?, ?)", (game_id, now))
            # Runtime is counted while a process inside the game folder is alive.
            if psutil is not None and self.settings.value("track_playtime", True, type=bool):
                self._active_play = {"game_id": game_id, "started": time.monotonic(),
                                     "last_seen": time.monotonic(),
                                     "install_dir": game["install_dir"] or (str(Path(path).parent) if not is_steam else ""),
                                     "exe_path": path, "steam": is_steam, "committed": 0}
                self.status_label.setText(f"正在统计「{game['name']}」运行时长…")
            self.refresh_games()
            return True
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", f"无法启动游戏：\n{exc}\n\nSteam 游戏需要安装并登录 Steam。")
            return False

    def _tick_playtime(self):
        active = getattr(self, "_active_play", None)
        if not active or psutil is None or not self.settings.value("track_playtime", True, type=bool):
            return
        now = time.monotonic()
        found = False
        install_dir = os.path.normcase(os.path.abspath(active.get("install_dir", ""))) if active.get("install_dir") else ""
        target_exe = os.path.normcase(os.path.abspath(active.get("exe_path", ""))) if not active.get("steam") else ""
        try:
            for proc in psutil.process_iter(["exe", "name"]):
                try:
                    exe = proc.info.get("exe") or ""
                    if not exe:
                        continue
                    normalized = os.path.normcase(os.path.abspath(exe))
                    if target_exe and normalized == target_exe:
                        found = True; break
                    if install_dir and (normalized == install_dir or normalized.startswith(install_dir + os.sep)):
                        found = True; break
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    continue
        except Exception:
            pass
        if found:
            active["last_seen"] = now
        # Give launchers a grace period to hand off to the actual game process.
        if now - active["last_seen"] > 35 and now - active["started"] > 35:
            elapsed = max(0, int(active["last_seen"] - active["started"]))
            if elapsed:
                with db_connect() as conn:
                    conn.execute("UPDATE games SET playtime_seconds=playtime_seconds+? WHERE id=?", (elapsed, active["game_id"]))
            self._active_play = None
            self.status_label.setText("运行时长已保存")
            self.refresh_games()

    def scan_steam_games(self):
        if getattr(self, "steam_worker", None) is not None:
            return
        self.steam_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        initial_message = "正在查找 Steam 库并获取封面…首次联网可能需要一些时间"
        self.status_label.setText(initial_message)
        self._show_scan_progress("steam", "正在识别 Steam 游戏", initial_message)

        def on_steam_progress(message):
            self.status_label.setText(message)
            self._show_scan_progress("steam", "正在识别 Steam 游戏", message)

        self.steam_worker = SteamScanWorker(
            download_covers=self.settings.value("auto_download_covers", True, type=bool),
            custom_path=self.settings.value("steam_path", "", type=str), parent=self
        )
        self.steam_worker.progress.connect(on_steam_progress)
        self.steam_worker.found.connect(self.on_steam_found)
        self.steam_worker.failed.connect(self.on_steam_failed)
        self.steam_worker.finished.connect(self.on_steam_finished)
        self.steam_worker.start()

    def on_steam_found(self, games):
        added = updated = skipped = 0
        with db_connect() as conn:
            for game in games:
                appid = game["appid"]
                exe = game.get("exe_path") or f"steam://rungameid/{appid}"
                existing = conn.execute("SELECT id, cover_path FROM games WHERE steam_appid=? OR exe_path=?", (appid, normalized_path(exe) if not exe.startswith("steam://") else exe)).fetchone()
                cover = game.get("cover_path", "")
                if (
                    not cover
                    and game.get("exe_path")
                    and os.path.isfile(game["exe_path"])
                    and not game["exe_path"].lower().startswith("steam://")
                ):
                    cover = extract_exe_icon_as_cover(game["exe_path"])
                if existing:
                    new_cover = cover if cover and not existing["cover_path"] else existing["cover_path"]
                    conn.execute("UPDATE games SET steam_appid=?, install_dir=?, cover_path=? WHERE id=?",
                                 (appid, game["install_dir"], new_cover, existing["id"]))
                    updated += 1
                    continue
                conn.execute("""INSERT OR IGNORE INTO games
                    (name, exe_path, category, cover_path, steam_appid, install_dir, created_at)
                    VALUES (?, ?, '其他', ?, ?, ?, ?)""", (
                    game["name"], normalized_path(exe) if not exe.startswith("steam://") else exe,
                    cover, appid, game["install_dir"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                if conn.execute("SELECT changes()").fetchone()[0]: added += 1
                else: skipped += 1
        self.refresh_games()
        detail = (
            f"发现已安装 Steam 游戏：{len(games)} 款\n"
            f"新增：{added} 款   补全封面/信息：{updated} 款   已存在或跳过：{skipped} 款\n"
            f"封面需要联网；网络不可用时仍可导入游戏。"
        )
        self._show_scan_progress("steam", "Steam 识别完成", detail, finished=True)

    def on_steam_failed(self, message):
        self._show_scan_progress("steam", "Steam 识别失败", message, failed=True)

    def on_steam_finished(self):
        self.steam_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.steam_worker = None
        self.status_label.setText("Steam 识别结束 · 本机离线库")

    def scan_directory(self):
        root = QFileDialog.getExistingDirectory(self, "选择要扫描的游戏目录", str(Path.home()))
        if not root:
            return
        self.scan_btn.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.status_label.setText("正在扫描目录…")
        self._show_scan_progress("game", "正在扫描游戏目录", f"正在扫描：{root}")
        self.scan_worker = ScanWorker(root)
        self.scan_worker.progress.connect(lambda message: self._show_scan_progress("game", "正在扫描游戏目录", message))
        self.scan_worker.found.connect(self.on_scan_found)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.start()

    def on_scan_found(self, paths):
        self._show_scan_progress("game", "游戏目录扫描完成", f"共发现 {len(paths)} 个 EXE 文件。", finished=True)
        with db_connect() as conn:
            known = {row["exe_path"] for row in conn.execute("SELECT exe_path FROM games")}
        candidates = [p for p in paths if normalized_path(p) not in known]
        if not candidates:
            QMessageBox.information(
                self, "扫描完成",
                f"本次扫描发现 {len(paths)} 个 EXE，没有发现尚未收录的文件。"
            )
            self.refresh_games()
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("扫描结果 · 选择要添加的游戏")
        dlg.resize(820, 600)
        layout = QVBoxLayout(dlg)
        intro = QLabel(
            f"共发现 {len(paths)} 个 EXE，其中 {len(candidates)} 个尚未收录。\n"
            "扫描结果可能包括启动器、更新器或游戏组件；请只勾选你确认的游戏主程序。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        search = QLineEdit()
        search.setPlaceholderText("输入路径关键词进行筛选…")
        layout.addWidget(search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)
        checks = []
        for p in candidates:
            cb = QCheckBox(p)
            cb.setToolTip(p)
            cb.setChecked(False)
            vbox.addWidget(cb)
            checks.append(cb)
        vbox.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        def filter_checks(text):
            term = text.lower().strip()
            for checkbox in checks:
                checkbox.setVisible(term in checkbox.text().lower())
        search.textChanged.connect(filter_checks)

        controls = QHBoxLayout()
        select_visible = QPushButton("全选当前筛选")
        clear_all = QPushButton("取消全选")
        select_visible.clicked.connect(
            lambda: [cb.setChecked(True) for cb in checks if cb.isVisible()]
        )
        clear_all.clicked.connect(lambda: [cb.setChecked(False) for cb in checks])
        controls.addWidget(select_visible)
        controls.addWidget(clear_all)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("添加选中项")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = [cb.text() for cb in checks if cb.isChecked()]
            imported = 0
            with db_connect() as conn:
                for p in selected:
                    try:
                        cover = extract_exe_icon_as_cover(p)
                        conn.execute("""
                            INSERT OR IGNORE INTO games (name, exe_path, category, cover_path, created_at)
                            VALUES (?, ?, '其他', ?, ?)
                        """, (
                            Path(p).stem, normalized_path(p), cover,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        ))
                        imported += conn.execute("SELECT changes()").fetchone()[0]
                    except sqlite3.Error:
                        continue
            QMessageBox.information(self, "导入完成", f"已添加 {imported} 款游戏。")
            self.refresh_games()

    def on_scan_failed(self, message):
        self._show_scan_progress("game", "游戏目录扫描失败", message, failed=True)
        QMessageBox.critical(self, "扫描失败", message)

    def on_scan_finished(self):
        self.scan_btn.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.scan_worker = None
        self.status_label.setText("扫描结束 · 本机离线库")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出游戏清单", "gameshelf_export.csv", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            columns = [
                "name", "exe_path", "launch_args", "category", "tags", "notes",
                "cover_path", "favorite", "play_count", "last_played", "playtime_seconds", "steam_appid", "install_dir"
            ]
            with db_connect() as conn, open(path, "w", newline="", encoding="utf-8-sig") as f:
                rows = conn.execute(f"SELECT {','.join(columns)} FROM games ORDER BY name").fetchall()
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows([tuple(row) for row in rows])
            self._show_message("导出成功", f"已导出 {len(rows)} 款游戏。")
        except Exception as exc:
            self._show_message("导出失败", str(exc))

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入游戏清单", "", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            imported = 0
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                required = {"name", "exe_path"}
                if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                    raise ValueError("CSV 至少需要包含 name 和 exe_path 两列。")
                with db_connect() as conn:
                    for row in reader:
                        raw_path = (row.get("exe_path") or "").strip()
                        name = (row.get("name") or Path(raw_path).stem).strip()
                        if not raw_path or not name:
                            continue
                        exe = normalized_path(raw_path)
                        try:
                            conn.execute("""
                                INSERT OR IGNORE INTO games
                                (name, exe_path, launch_args, category, tags, notes, cover_path,
                                 favorite, play_count, last_played, playtime_seconds, steam_appid, install_dir, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                name, exe, row.get("launch_args", ""), row.get("category", "其他"),
                                row.get("tags", ""), row.get("notes", ""), row.get("cover_path", ""),
                                int(row.get("favorite") or 0), int(row.get("play_count") or 0),
                                row.get("last_played", ""), int(row.get("playtime_seconds") or 0), row.get("steam_appid", ""), row.get("install_dir", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            ))
                            imported += conn.execute("SELECT changes()").fetchone()[0]
                        except (sqlite3.Error, ValueError):
                            continue
            self.refresh_games()
            self._show_message("导入完成", f"成功新增 {imported} 条记录。重复路径已跳过。")
        except Exception as exc:
            self._show_message("导入失败", str(exc))


def main():
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("GameShelf")  # Preserve the existing QSettings namespace.
    language = QSettings("GameShelf", "GameShelf").value("language", "zh_CN", type=str)
    set_language(language)
    if LOGO_ICO_PATH.exists():
        app.setWindowIcon(QIcon(str(LOGO_ICO_PATH)))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    titlebar_filter = NativeTitleBarThemeFilter(app)
    app.installEventFilter(titlebar_filter)
    window = GameShelfWindow()
    try:
        app.styleHints().colorSchemeChanged.connect(window.apply_system_theme)
    except (AttributeError, TypeError):
        pass
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()