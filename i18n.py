"""Tutler bilingual UI translations and Qt text hooks.

Keep Chinese/English UI text and translation rules here rather than in main.py.
"""
import re
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QLabel, QPushButton, QCheckBox, QLineEdit, QWidget, QTabWidget,
    QComboBox, QMessageBox, QInputDialog, QFileDialog,
    QFormLayout, QDialogButtonBox,
)
# --- Tutler bilingual UI layer (generated from the Chinese and English editions) ---
import re as _tutler_re
CURRENT_LANGUAGE = "zh_CN"
_TRANSLATIONS = {
    "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)": "Image files (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
    "其他": "Other",
    "TEXT DEFAULT '其他'": "TEXT DEFAULT 'Other'",
    "把封面复制到应用自己的数据目录，避免原图片被移动后失效。": "Copy the cover into the app data directory so moving the original image will not break it.",
    "过滤崩溃处理器、卸载器、运行库安装器等非游戏主程序。": "Filter out non-game executables such as crash handlers, uninstallers, and runtime installers.",
    "递归发现可能的游戏 EXE，同时跳过常见安装器和辅助组件目录。": "Recursively find possible game executables while skipping common installer and helper-component directories.",
    "按游戏名、目录位置和文件体积排序，尽量选出真正的游戏主程序。": "Rank executables by game name, directory, and file size to identify the most likely main executable.",
    "把图标提取的诊断信息写入日志文件，便于定位失败原因。": "Write icon-extraction diagnostics to a log file to help troubleshoot failures.",
    "▶\n视频预览生成中": "▶\nGenerating video preview",
    "▶\n视频封面需要 FFmpeg": "▶\nFFmpeg is required for video thumbnails",
    "视频预览帧": "Video preview frame",
    "安装 FFmpeg 并重新打开视频库可生成视频封面": "Install FFmpeg and reopen the video library to generate thumbnails",
    "大小未知": "Unknown size",
    "分类": "Category",
    "（无分类）": "(Uncategorized)",
    "▶  播放": "▶  Play",
    "移除": "Remove",
    "仅从 Tutler 视频库中移除，不会删除硬盘上的视频文件": "Remove from Tutler video library only; the video file on disk will not be deleted",
    "图片预览不可用": "Image preview unavailable",
    "打开图片": "Open Image",
    "仅从 Tutler 图片库中移除，不会删除硬盘上的图片文件": "Remove from Tutler image library only; the image file on disk will not be deleted",
    "编辑游戏": "Edit Game",
    "添加游戏": "Add Game",
    "例如：D:\\Games\\MyGame\\Game.exe": "Example: D:\\Games\\MyGame\\Game.exe",
    "可选，例如：-windowed -language \"zh-CN\"": "Optional, e.g.: -windowed -language \"zh-CN\"",
    "动作, 单机, 手柄": "Action, Single-player, Controller",
    "浏览…": "Browse…",
    "尚未选择封面": "No cover selected",
    "选择图片…": "Choose Image…",
    "清除": "Clear",
    "游戏名称": "Game Name",
    "游戏 EXE": "Game Executable",
    "启动参数": "Launch Arguments",
    "游戏分类": "Game Category",
    "标签": "Tags",
    "游戏封面": "Game Cover",
    "备注": "Notes",
    "封面会复制到 Tutler 的本地数据目录。移除游戏记录不会删除游戏本体。": "The cover is copied to Tutler’s local data directory. Removing a game entry will not delete the game itself.",
    "选择游戏可执行文件": "Select Game Executable",
    "Windows 程序 (*.exe);;所有文件 (*.*)": "Windows Executables (*.exe);;All Files (*.*)",
    "选择游戏封面": "Choose Game Cover",
    "无法读取或复制所选图片。": "Could not read or copy the selected image.",
    "封面设置失败": "Failed to Set Cover",
    "信息不完整": "Missing Information",
    "请输入游戏名称。": "Please enter a game name.",
    "路径无效": "Invalid Path",
    "请选择一个存在的 EXE 文件或有效的 Steam 游戏。": "Select an existing EXE file or a valid Steam game.",
    "文件类型不支持": "Unsupported File Type",
    "第一版仅支持 Windows .exe 文件。": "This version only supports Windows .exe files.",
    "取消收藏": "Remove from Favorites",
    "加入收藏": "Add to Favorites",
    "最近游玩  ": "Last Played  ",
    "▶  启动游戏": "▶  Launch Game",
    "编辑": "Edit",
    "绘制像素尺寸统一的窗口控制图标，避免不同字体导致符号大小不一。": "Draw window-control icons with consistent pixel dimensions so glyph sizes do not vary by font.",
    "最小化": "Minimize",
    "最大化": "Maximize",
    "还原": "Restore",
    "关闭": "Close",
    "轻量自绘标题栏：统一品牌区与窗口控制按钮。": "A lightweight custom title bar that unifies branding and window controls.",
    "未分类": "Uncategorized",
    "电影": "Movies",
    "电视剧": "TV Shows",
    "动画": "Animation",
    "纪录片": "Documentaries",
    "课程": "Courses",
    "游戏库": "Game Library",
    "全部游戏": "All Games",
    "我的收藏": "Favorites",
    "＋  自定义分类": "+  Custom Category",
    "↕  排序/管理游戏分类": "↕  Sort / Manage Game Categories",
    "视频库": "Video Library",
    "全部视频": "All Videos",
    "＋  自定义视频分类": "+  Custom Video Category",
    "↕  排序/管理视频分类": "↕  Sort / Manage Video Categories",
    "图片库": "Image Library",
    "全部图片": "All Images",
    "＋  自定义图片分类": "+  Custom Image Category",
    "↕  排序/管理图片分类": "↕  Sort / Manage Image Categories",
    "⚙    应用设置": "⚙    Settings",
    "本机数据 · 离线可用": "Local data · Available offline",
    "管理并启动你电脑上的游戏": "Manage and launch games on your PC",
    "+ 添加游戏": "+ Add Game",
    "⌕  扫描目录": "⌕  Scan Folder",
    "♨  识别 Steam": "♨  Detect Steam",
    "＋ 添加视频目录": "+ Add Video Folder",
    "＋ 添加图片目录": "+ Add Image Folder",
    "⌕   搜索游戏名称、路径或标签…": "⌕   Search game names, paths, or tags…",
    "最近添加": "Recently Added",
    "名称 A-Z": "Name A-Z",
    "最近游玩": "Recently Played",
    "启动次数": "Launch Count",
    "导入": "Import",
    "导出": "Export",
    "0 款游戏": "0 games",
    "只更新游戏分类子树的展开状态，不参与页面导航按钮的选中状态。": "Update only the expanded state of the game-category subtree; do not affect page-navigation selection.",
    "新增游戏分类": "Add Game Category",
    "请输入分类名称（如 SURVIVAL、SANDBOX）：": "Enter a category name (e.g. SURVIVAL, SANDBOX):",
    "分类名称不能为空": "Category name cannot be empty",
    "请输入一个分类名称。": "Please enter a category name.",
    "分类已存在": "Category already exists",
    "新增视频分类": "Add Video Category",
    "请输入视频分类名称：": "Enter a video category name:",
    "新增图片分类": "Add Image Category",
    "请输入图片分类名称：": "Enter an image category name:",
    "视频分类排序与管理": "Sort and Manage Video Categories",
    "图片分类排序与管理": "Sort and Manage Image Categories",
    "游戏分类排序与管理": "Sort and Manage Game Categories",
    "选中分类后使用上移/下移调整左侧顺序。自定义分类可删除；删除分类不会删除媒体或游戏文件。视频库和图片库默认没有预置分类。": "Select a category and use Move Up / Move Down to change its order. Custom categories can be deleted; deleting a category does not delete media or game files. The video and image libraries have no preset categories.",
    "内置分类（不可删除）": "Built-in category (cannot be deleted)",
    "自定义分类": "Custom category",
    "上移": "Move Up",
    "下移": "Move Down",
    "删除自定义分类": "Delete Custom Category",
    "恢复默认设置": "Restore Defaults",
    "请选择分类": "Select a Category",
    "请先选择要删除的分类。": "Select a category to delete first.",
    "不能删除": "Cannot Delete",
    "内置分类不能删除。": "Built-in categories cannot be deleted.",
    "确认删除自定义分类": "Confirm Delete Custom Category",
    "该分类下的资源将变为无分类。只删除分类设置，不会删除硬盘上的文件。": "Resources in this category will become uncategorized. Only the category setting is deleted; files on disk will remain.",
    "该分类下的游戏将移至 OTHER。只删除分类设置，不会删除游戏文件。": "Games in this category will be moved to OTHER. Only the category setting is deleted; game files will remain.",
    "取消": "Cancel",
    "删除分类": "Delete Category",
    "分类已删除": "Category Deleted",
    "分类排序已保存": "Category Order Saved",
    "分类顺序已更新并保存，没有删除分类。": "Category order updated and saved; no categories were deleted.",
    "没有删除分类": "No Categories Deleted",
    "本次没有删除任何分类，分类设置未发生变化。": "No categories were deleted; category settings remain unchanged.",
    "高度动画使用当前 maximumHeight 作为起点，支持中途反向和快速切换。": "Height animations start from the current maximumHeight, allowing reversal and rapid switching.",
    "资源库互斥展开：切换时先彻底隐藏旧库，只动画新打开的父容器。": "Library sections expand exclusively: fully hide the previous library before animating the newly opened parent container.",
    "由视图切换调用，保证资源库展开状态与当前视图一致。": "Called during view changes to keep the expanded library in sync with the current view.",
    "打开资源库时进入该库的根页面；折叠操作不改变当前页面。": "Opening a library navigates to its root page; collapsing it does not change the current page.",
    "文件": "File",
    "扫描游戏目录": "Scan Game Folder",
    "导入 CSV 清单": "Import CSV List",
    "导出 CSV 清单": "Export CSV List",
    "退出": "Exit",
    "应用设置…": "Settings…",
    "帮助": "Help",
    "关于 Tutler": "About Tutler",
    "统一主题、文字对比度、对话框和控件圆角。": "Unify the theme, text contrast, dialog appearance, and control corner radii.",
    "关闭 Tutler": "Close Tutler",
    "你希望如何处理 Tutler？": "What would you like to do with Tutler?",
    "最小化": "Minimize",
    "关闭程序": "Quit Application",
    "取消": "Cancel",
    "语言更改后需要重启应用才能生效。": "Restart the app for the language change to take effect.",
    "正在识别 Steam 游戏…": "Detecting Steam games…",
    "封面需要联网；网络不可用时仍可导入游戏。": "Internet is required for covers; games can still be imported offline.",
    "Tutler 应用设置": "Tutler Settings",
    "应用主题": "Application Theme",
    "跟随系统": "Follow System",
    "深色": "Dark",
    "亮色": "Light",
    "识别 Steam 时自动下载游戏封面（需要网络）": "Automatically download game covers when detecting Steam games (Internet required)",
    "启动应用时自动识别 Steam 游戏": "Automatically detect Steam games on startup",
    "统计游戏运行时长（需要安装 psutil）": "Track game playtime (requires psutil)",
    "界面": "Appearance",
    "Steam 安装路径（可选；留空则自动识别）": "Steam installation path (optional; leave blank for automatic detection)",
    "例如：C:\\Program Files (x86)\\Steam": "Example: C:\\Program Files (x86)\\Steam",
    "自动识别": "Auto-detect",
    "路径留空时会搜索常见安装位置和 Windows 注册表。": "If the path is blank, common installation locations and the Windows Registry will be searched.",
    "选择 Steam 安装目录": "Select Steam Installation Folder",
    "未找到 Steam。请手动选择包含 steam.exe 或 steamapps 文件夹的目录。": "Steam was not found. Select a folder containing steam.exe or the steamapps folder.",
    "点击窗口右上角关闭按钮时": "When the window close button in the upper-right corner is clicked",
    "每次询问（最小化 / 关闭程序 / 取消）": "Ask every time (Minimize / Quit / Cancel)",
    "最小化窗口": "Minimize Window",
    "直接关闭程序": "Quit Application",
    "选择“最小化窗口”后，点击关闭按钮会将窗口最小化到任务栏，不会退出进程。": "When Minimize Window is selected, the close button minimizes the window to the taskbar without exiting the process.",
    "启动游戏前显示确认提示": "Ask for confirmation before launching a game",
    "窗口": "Window",
    "本地 PC 游戏管理器": "Local PC Game Manager",
    "关于": "About",
    "保存设置": "Save Settings",
    "设置已保存": "Settings Saved",
    "主题立即生效；Steam 路径将在下次扫描时使用，启动时自动识别将在下次启动时执行。": "The theme takes effect immediately. The Steam path will be used on the next scan, and automatic detection will run on the next launch.",
    "浏览本机视频文件，点击后使用 Windows 默认视频播放器打开": "Browse local video files and click to open them in the default Windows video player",
    "搜索视频名称或文件路径…": "Search video names or file paths…",
    "浏览本机图片文件，点击后使用 Windows 默认图片查看器打开": "Browse local image files and click to open them in the default Windows image viewer",
    "搜索图片名称或文件路径…": "Search image names or file paths…",
    "快速访问你最喜欢的游戏": "Quickly access your favorite games",
    "查看最近启动过的游戏": "View recently launched games",
    "本机离线库": "Local offline library",
    "这里暂时没有游戏\n\n点击「添加游戏」或「扫描目录」开始建立你的游戏库。": "No games here yet\n\nClick Add Game or Scan Folder to start building your library.",
    "选择视频目录": "Select Video Folder",
    "正在扫描视频目录…": "Scanning video folders…",
    "正在扫描视频目录": "Scanning Video Folders",
    "视频扫描完成": "Video Scan Complete",
    "视频扫描失败": "Video Scan Failed",
    "为库中尚无封面、且 EXE 仍然存在的游戏批量提取 EXE 图标作为封面。": "Batch-extract EXE icons as covers for games that have no cover and whose EXE still exists.",
    "封面已补全": "Covers Completed",
    "还没有视频资源\n\n点击「添加视频目录」，选择包含视频的文件夹开始扫描。\n视频库默认没有分类；可使用左侧「自定义视频分类」创建自己的分类。\n支持 MP4、MKV、AVI、MOV、WMV、WebM 等常见格式。": "No videos yet\n\nClick Add Video Folder and select a folder containing videos to scan.\nThe video library has no default categories; use Custom Video Category on the left to create categories.\nCommon formats include MP4, MKV, AVI, MOV, WMV, and WebM.",
    "选择图片目录": "Select Image Folder",
    "正在扫描图片目录…": "Scanning image folders…",
    "正在扫描图片目录": "Scanning Image Folders",
    "图片扫描完成": "Image Scan Complete",
    "图片扫描失败": "Image Scan Failed",
    "还没有图片资源\n\n点击「添加图片目录」，选择包含图片的文件夹开始扫描。\n图片库默认没有分类；可通过左侧「自定义图片分类」创建分类。": "No images yet\n\nClick Add Image Folder and select a folder containing images to scan.\nThe image library has no default categories; use Custom Image Category on the left to create categories.",
    "从视频库移除": "Remove from Video Library",
    "只会移除视频库记录及其分类信息，不会删除硬盘上的视频文件。": "Only the video-library entry and its category information will be removed; the video file on disk will remain.",
    "移除视频": "Remove Video",
    "已移除视频": "Video Removed",
    "从图片库移除": "Remove from Image Library",
    "只会移除图片库记录及其分类信息，不会删除硬盘上的图片文件。": "Only the image-library entry and its category information will be removed; the image file on disk will remain.",
    "移除图片": "Remove Image",
    "已移除图片": "Image Removed",
    "图片不存在": "Image Not Found",
    "系统未能打开此图片文件": "The system could not open this image file",
    "无法打开图片": "Unable to Open Image",
    "视频不存在": "Video Not Found",
    "系统未能打开此视频文件": "The system could not open this video file",
    "无法播放视频": "Unable to Play Video",
    "重复路径": "Duplicate Path",
    "这个 EXE 已经在游戏库中了。每个 EXE 路径只能收录一次。": "This EXE is already in the game library. Each EXE path can only be added once.",
    "保存失败": "Save Failed",
    "确认": "Confirm",
    "移除游戏": "Remove Game",
    "只会删除游戏库记录和启动历史，不会删除游戏文件。": "Only the game-library entry and launch history will be removed; the game files will remain.",
    "找不到游戏": "Game Not Found",
    "启动游戏": "Launch Game",
    "缺少 Steam AppID": "Missing Steam AppID",
    "启动失败": "Launch Failed",
    "运行时长已保存": "Playtime Saved",
    "正在查找 Steam 库并获取封面…首次联网可能需要一些时间": "Searching Steam libraries and retrieving covers… the first online run may take some time",
    "正在识别 Steam 游戏": "Detecting Steam Games",
    "Steam 识别完成": "Steam Detection Complete",
    "Steam 识别失败": "Steam Detection Failed",
    "Steam 识别结束 · 本机离线库": "Steam detection finished · Local offline library",
    "选择要扫描的游戏目录": "Select a Game Folder to Scan",
    "正在扫描目录…": "Scanning folder…",
    "正在扫描游戏目录": "Scanning Game Folder",
    "游戏目录扫描完成": "Game Folder Scan Complete",
    "扫描完成": "Scan Complete",
    "扫描结果 · 选择要添加的游戏": "Scan Results · Select Games to Add",
    "扫描结果可能包括启动器、更新器或游戏组件；请只勾选你确认的游戏主程序。": "Results may include launchers, updaters, or game components; select only executables you recognize as main game programs.",
    "输入路径关键词进行筛选…": "Filter by path keywords…",
    "全选当前筛选": "Select All Visible",
    "取消全选": "Clear Selection",
    "添加选中项": "Add Selected",
    "导入完成": "Import Complete",
    "游戏目录扫描失败": "Game Folder Scan Failed",
    "扫描失败": "Scan Failed",
    "扫描结束 · 本机离线库": "Scan finished · Local offline library",
    "导出游戏清单": "Export Game List",
    "CSV 文件 (*.csv)": "CSV Files (*.csv)",
    "导出成功": "Export Successful",
    "导出失败": "Export Failed",
    "导入游戏清单": "Import Game List",
    "CSV 至少需要包含 name 和 exe_path 两列。": "The CSV must contain at least the name and exe_path columns.",
    "导入失败": "Import Failed"
}
_TRANSLATIONS.update({
    '界面语言': 'Interface Language',
    '简体中文': '简体中文 (Chinese)',
    '语言设置已保存': 'Language Preference Saved',
    '语言将在重新启动 Tutler 后生效。': 'The language change will take effect after restarting Tutler.',
})

# Additional coverage for navigation headers, close prompts, settings tabs, and About paths.
_TRANSLATIONS.update({
    "游戏库": "Game Library",
    "视频库": "Video Library",
    "图片库": "Image Library",
    "最小化": "Minimize",
    "关闭 Tutler": "Close Tutler",
    "你希望如何处理 Tutler？": "What would you like to do with Tutler?",
    "最小化": "Minimize",
    "关闭程序": "Quit Application",
    "取消": "Cancel",
    "语言更改后需要重启应用才能生效。": "Restart the app for the language change to take effect.",
    "正在识别 Steam 游戏…": "Detecting Steam games…",
    "封面需要联网；网络不可用时仍可导入游戏。": "Internet is required for covers; games can still be imported offline.",
    "界面": "Appearance",
    "Steam": "Steam",
    "窗口": "Window",
    "关于": "About",
    "当前版本：": "Version: ",
    "本地 PC 游戏管理器": "Local PC Game Manager",
    "数据目录：": "Data directory: ",
    "数据库：": "Database: ",
    "游戏文件不会被复制、移动或删除。": "Game files are never copied, moved, or deleted.",
})
# These labels are composed dynamically, so exact dictionary lookup is not enough.
_EARLY_EXTRA_TRANSLATION_PATTERNS = [
    (re.compile(r'^[▾▸]\s*游戏库$'), ['Game Library']),
    (re.compile(r'^[▾▸]\s*视频库$'), ['Video Library']),
    (re.compile(r'^[▾▸]\s*图片库$'), ['Image Library']),
    (re.compile(r'^数据目录：(.*?)\n数据库：(.*?)$'), ['Data directory: ', ('GROUP', 1), '\nDatabase: ', ('GROUP', 2)]),
    (re.compile(r'^Tutler (.*?)\n本地 PC 游戏、视频与图片管理器\n\n数据库：\n(.*?)\n\n游戏文件不会被复制、移动或删除。$'), ['Tutler ', ('GROUP', 1), '\nLocal PC game, video, and image manager\n\nDatabase:\n', ('GROUP', 2), '\n\nGame files are never copied, moved, or deleted.']),
]
_TRANSLATION_PATTERNS = [
    (re.compile('^文件不存在，跳过：(.*?)$'), ['File does not exist; skipping: ', ('GROUP', 1)]),
    (re.compile('^Qt\\ 组件导入失败：(.*?)$'), ['Failed to import Qt components: ', ('GROUP', 1)]),
    (re.compile('^QFileIconProvider\\ 未获得有效图标：(.*?)（sizes=(.*?)）$'), ['QFileIconProvider returned no valid icon: ', ('GROUP', 1), '（sizes=', ('GROUP', 2), '）']),
    (re.compile('^QFileIconProvider\\ 失败：(.*?)\\ \\->\\ (.*?)$'), ['QFileIconProvider failed: ', ('GROUP', 1), ' -> ', ('GROUP', 2)]),
    (re.compile('^SHGetFileInfo\\ 句柄转\\ QPixmap\\ 失败：(.*?)$'), ['Failed to convert the SHGetFileInfo handle to QPixmap: ', ('GROUP', 1)]),
    (re.compile('^SHGetFileInfo\\ 返回空句柄：(.*?)$'), ['SHGetFileInfo returned an empty handle: ', ('GROUP', 1)]),
    (re.compile('^SHGetFileInfo\\ 失败：(.*?)\\ \\->\\ (.*?)$'), ['SHGetFileInfo failed: ', ('GROUP', 1), ' -> ', ('GROUP', 2)]),
    (re.compile('^ExtractIconEx\\ 句柄转\\ QPixmap\\ 失败：(.*?)$'), ['Failed to convert the ExtractIconEx handle to QPixmap: ', ('GROUP', 1)]),
    (re.compile('^ExtractIconEx\\ 未提取到图标：(.*?)$'), ['ExtractIconEx did not extract an icon: ', ('GROUP', 1)]),
    (re.compile('^ExtractIconEx\\ 失败：(.*?)\\ \\->\\ (.*?)$'), ['ExtractIconEx failed: ', ('GROUP', 1), ' -> ', ('GROUP', 2)]),
    (re.compile('^所有方式均失败，放弃：(.*?)$'), ['All methods failed; giving up: ', ('GROUP', 1)]),
    (re.compile('^PNG\\ 保存失败：(.*?)$'), ['Failed to save PNG: ', ('GROUP', 1)]),
    (re.compile('^合成封面失败：(.*?)\\ \\->\\ (.*?)$'), ['Failed to compose cover: ', ('GROUP', 1), ' -> ', ('GROUP', 2)]),
    (re.compile(r'^正在识别 Steam 游戏…(.*?)/(.*?)：(.*?)$'), ['Detecting Steam games… ', ('GROUP', 1), '/', ('GROUP', 2), ': ', ('GROUP', 3)]),
    (re.compile('^正在扫描…已发现\\ (.*?)\\ 个\\ EXE$'), ['Scanning… found ', ('GROUP', 1), ' EXE files']),
    (re.compile('^正在扫描视频…已发现\\ (.*?)\\ 个文件$'), ['Scanning videos… found ', ('GROUP', 1), '  files']),
    (re.compile('^正在扫描图片…已发现\\ (.*?)\\ 个文件$'), ['Scanning images… found ', ('GROUP', 1), '  files']),
    (re.compile('^显示「(.*?)」分类中的游戏$'), ['Show “', ('GROUP', 1), '”']),
    (re.compile('^显示「(.*?)」视频分类$'), ['Show “', ('GROUP', 1), '” video category']),
    (re.compile('^显示「(.*?)」图片分类$'), ['Show “', ('GROUP', 1), '” image category']),
    (re.compile('^「(.*?)」已经存在，无需重复添加。$'), ['「', ('GROUP', 1), '” already exists; there is no need to add it again.']),
    (re.compile('^「(.*?)」已经存在。$'), ['「', ('GROUP', 1), '” already exists.']),
    (re.compile('^「(.*?)」已经存在。$'), ['「', ('GROUP', 1), '” already exists.']),
    (re.compile('^确定删除分类「(.*?)」吗？$'), ['Delete category “', ('GROUP', 1), '” from Tutler?']),
    (re.compile('^已删除\\ (.*?)\\ 个自定义分类，相关资源已移至无分类/默认分类。$'), ['Deleted ', ('GROUP', 1), ' custom categories; related resources were moved to Uncategorized / the default category.']),
    (re.compile('^已识别路径：(.*?)$'), ['Detected path: ', ('GROUP', 1)]),
    (re.compile('^当前版本：(.*?)$'), ['Version: ', ('GROUP', 1)]),
    (re.compile('^数据目录：(.*?)\\\\n数据库：(.*?)$'), ['Data directory: ', ('GROUP', 1), '\\nDatabase: ', ('GROUP', 2)]),
    (re.compile('^Tutler\\ (.*?)\\\\n本地\\ PC\\ 游戏、视频与图片管理器\\\\n\\\\n数据库：\\\\n(.*?)\\\\n\\\\n游戏文件不会被复制、移动或删除。$'), ['Tutler ', ('GROUP', 1), '\\nLocal PC game, video, and image manager\\n\\nDatabase: \\n', ('GROUP', 2), '\\n\\nGame files are never copied, moved, or deleted.']),
    (re.compile('^分类：(.*?)$'), ['Category: ', ('GROUP', 1)]),
    (re.compile('^(.*?)\\ 款游戏$'), [('GROUP', 1), '  games']),
    (re.compile('^正在检查\\ (.*?)\\ 个目录…$'), ['Checking ', ('GROUP', 1), ' folder(s)…']),
    (re.compile('^已找到\\ (.*?)\\ 个视频文件$'), ['Found ', ('GROUP', 1), ' video file(s)']),
    (re.compile('^共找到\\ (.*?)\\ 个视频文件。$'), ['Found a total of ', ('GROUP', 1), ' video file(s)。']),
    (re.compile('^其中\\ (.*?)\\ 个已归入分类「(.*?)」。$'), ['of which ', ('GROUP', 1), ' item(s) were assigned to category “', ('GROUP', 2), '”.']),
    (re.compile('^已为\\ (.*?)\\ 款游戏提取\\ EXE\\ 图标作为封面。$'), ['Extracted covers for ', ('GROUP', 1), ' game(s) from their EXE icons.']),
    (re.compile('^(.*?)\\ 个视频$'), [('GROUP', 1), ' video(s)']),
    (re.compile('^视频目录：(.*?)\\ 个$'), ['Video folders: ', ('GROUP', 1)]),
    (re.compile('^已生成\\ (.*?)\\ 张视频封面$'), ['Generated ', ('GROUP', 1), ' video thumbnail(s)']),
    (re.compile('^正在检查\\ (.*?)\\ 个目录…$'), ['Checking ', ('GROUP', 1), ' folder(s)…']),
    (re.compile('^已找到\\ (.*?)\\ 张图片$'), ['Found ', ('GROUP', 1), ' image(s)']),
    (re.compile('^共找到\\ (.*?)\\ 张图片。$'), ['Found a total of ', ('GROUP', 1), ' image(s)。']),
    (re.compile('^其中\\ (.*?)\\ 张已归入分类「(.*?)」。$'), ['of which ', ('GROUP', 1), " item(s) were assigned to category '", ('GROUP', 2), "'."]),
    (re.compile('^(.*?)\\ 张图片$'), [('GROUP', 1), ' image(s)']),
    (re.compile('^图片目录：(.*?)\\ 个$'), ['Image folders: ', ('GROUP', 1)]),
    (re.compile('^确定从\\ Tutler\\ 视频库中移除「(.*?)」吗？$'), ['Remove “', ('GROUP', 1), '” from Tutler?']),
    (re.compile('^「(.*?)」已从视频库移除，原文件未删除。$'), ['「', ('GROUP', 1), '」was removed from the video library; the original file was not deleted.']),
    (re.compile('^确定从\\ Tutler\\ 图片库中移除「(.*?)」吗？$'), ["Remove '", ('GROUP', 1), "' from the Tutler Image Library?"]),
    (re.compile('^「(.*?)」已从图片库移除，原文件未删除。$'), ['「', ('GROUP', 1), '」was removed from the image library; the original file was not deleted.']),
    (re.compile('^找不到图片文件：\\\\n(.*?)\\\\n请重新扫描图片目录。$'), ['Image file not found: \\n', ('GROUP', 1), '\\nPlease rescan the image folders.']),
    (re.compile('^已请求图片查看器打开：(.*?)$'), ['Requested image viewer to open: ', ('GROUP', 1)]),
    (re.compile('^无法调用系统默认图片查看器：\\\\n(.*?)$'), ['Could not launch the default image viewer: \\n', ('GROUP', 1)]),
    (re.compile('^找不到视频文件：\\\\n(.*?)\\\\n请重新扫描视频目录。$'), ['Video file not found: \\n', ('GROUP', 1), '\\nPlease rescan the video folders.']),
    (re.compile('^已请求播放器打开：(.*?)$'), ['Requested media player to open: ', ('GROUP', 1)]),
    (re.compile('^无法调用系统默认播放器：\\\\n(.*?)$'), ['Could not launch the default media player: \\n', ('GROUP', 1)]),
    (re.compile('^确定从\\ Tutler\\ 中移除「(.*?)」吗？$'), ["Remove '", ('GROUP', 1), "' from Tutler?"]),
    (re.compile('^文件不存在：\\\\n(.*?)\\\\n\\\\n如果游戏移动了位置，请编辑游戏并更新路径。$'), ['File not found: \\n', ('GROUP', 1), '\\n\\nIf the game has moved, edit the game entry and update its path.']),
    (re.compile('^确定启动「(.*?)」吗？$'), ['Launch “', ('GROUP', 1), '” from Tutler?']),
    (re.compile('^正在统计「(.*?)」运行时长…$'), ['Tracking playtime for “', ('GROUP', 1), '”…']),
    (re.compile('^无法启动游戏：\\\\n(.*?)\\\\n\\\\nSteam\\ 游戏需要安装并登录\\ Steam。$'), ['Could not launch game: \\n', ('GROUP', 1), '\\n\\nSteam games require Steam to be installed and signed in.']),
    (re.compile('^发现已安装\\ Steam\\ 游戏：(.*?)\\ 款\\\\n$'), ['Installed Steam games found: ', ('GROUP', 1), '\\n']),
    (re.compile('^新增：(.*?)\\ 款\\ \\ \\ 补全封面/信息：(.*?)\\ 款\\ \\ \\ 已存在或跳过：(.*?)\\ 款\\\\n$'), ['Added: ', ('GROUP', 1), '    Covers/details updated: ', ('GROUP', 2), '    Already present or skipped: ', ('GROUP', 3), '\\n']),
    (re.compile('^正在扫描：(.*?)$'), ['Scanning: ', ('GROUP', 1)]),
    (re.compile('^共发现\\ (.*?)\\ 个\\ EXE\\ 文件。$'), ['Found a total of ', ('GROUP', 1), ' EXE file(s).']),
    (re.compile('^本次扫描发现\\ (.*?)\\ 个\\ EXE，没有发现尚未收录的文件。$'), ['This scan found ', ('GROUP', 1), ' EXE files; no untracked files were found.']),
    (re.compile(r'^共发现 (.*?) 个 EXE，其中 (.*?) 个尚未收录。\n扫描结果可能包括启动器、更新器或游戏组件；请只勾选你确认的游戏主程序。$', re.S),
     ['Found ', ('GROUP', 1), ' EXE files, of which ', ('GROUP', 2), ' have not been added yet.\nResults may include launchers, updaters, or game components; select only executables you recognize as main game programs.']),    (re.compile('^已添加\\ (.*?)\\ 款游戏。$'), ['Added ', ('GROUP', 1), '  game(s).']),
    (re.compile('^已导出\\ (.*?)\\ 款游戏。$'), ['Exported ', ('GROUP', 1), '  game(s).']),
    (re.compile('^成功新增\\ (.*?)\\ 条记录。重复路径已跳过。$'), ['Successfully added ', ('GROUP', 1), ' record(s). Duplicate paths were skipped.']),
]
# Initialize the pattern list above before adding supplemental patterns.
_TRANSLATION_PATTERNS.extend(_EARLY_EXTRA_TRANSLATION_PATTERNS)
# Supplemental translations for library headers, category prompts, close dialog,
# settings tabs, and the About page. Keep these AFTER the pattern list is created.
_TRANSLATIONS.update({
    "新增游戏分类": "Add Game Category",
    "请输入分类名称（如 SURVIVAL、SANDBOX）：": "Enter a category name (e.g. SURVIVAL, SANDBOX):",
    "新增视频分类": "Add Video Category",
    "请输入视频分类名称：": "Enter a video category name:",
    "新增图片分类": "Add Image Category",
    "请输入图片分类名称：": "Enter an image category name:",
    "分类名称不能为空": "Category name cannot be empty",
    "请输入一个分类名称。": "Please enter a category name.",
    "分类已存在": "Category already exists",
    "关闭 Tutler": "Close Tutler",
    "你希望如何处理 Tutler？": "What would you like to do with Tutler?",
    "最小化": "Minimize",
    "关闭程序": "Quit Application",
    "取消": "Cancel",
    "Tutler 应用设置": "Tutler Settings",
    "界面语言": "Interface Language",
    "简体中文": "Chinese (Simplified)",
    "应用主题": "Application Theme",
    "跟随系统": "Follow System",
    "深色": "Dark",
    "亮色": "Light",
    "界面": "Appearance",
    "Steam": "Steam",
    "窗口": "Window",
    "关于": "About",
    "保存设置": "Save Settings",
    "当前版本：": "Version: ",
    "本地 PC 游戏、视频与图片管理器": "Local PC game, video, and image manager",
    "本地 PC 游戏管理器": "Local PC game manager",
    "数据目录：": "Data directory: ",
    "数据库：": "Database: ",
    "游戏文件不会被复制、移动或删除。": "Game files are never copied, moved, or deleted.",
    "选择 Steam 安装目录": "Select Steam Installation Folder",
    "已识别路径：": "Detected path: ",
    "未找到 Steam。请手动选择包含 steam.exe 或 steamapps 文件夹的目录。": "Steam was not found. Select a folder containing steam.exe or the steamapps folder.",
})
_TRANSLATION_PATTERNS.extend([
    (re.compile(r'^发现已安装 Steam 游戏：(.*?) 款\n新增：(.*?) 款   补全封面/信息：(.*?) 款   已存在或跳过：(.*?) 款\n封面需要联网；网络不可用时仍可导入游戏。$', re.S), ['Installed Steam games found: ', ('GROUP', 1), '\nAdded: ', ('GROUP', 2), '    Covers/details updated: ', ('GROUP', 3), '    Already present or skipped: ', ('GROUP', 4), '\nInternet is required for covers; games can still be imported offline.']),
    (re.compile(r'^[▾▸]\s*游戏库$'), ['Game Library']),
    (re.compile(r'^[▾▸]\s*视频库$'), ['Video Library']),
    (re.compile(r'^[▾▸]\s*图片库$'), ['Image Library']),
    (re.compile(r'^数据目录：(.*?)\n数据库：(.*?)$', re.S), ['Data directory: ', ('GROUP', 1), '\nDatabase: ', ('GROUP', 2)]),
    (re.compile(r'^Tutler (.*?)\n本地 PC 游戏、视频与图片管理器\n\n数据库：\n(.*?)\n\n游戏文件不会被复制、移动或删除。$', re.S), ['Tutler ', ('GROUP', 1), '\nLocal PC game, video, and image manager\n\nDatabase:\n', ('GROUP', 2), '\n\nGame files are never copied, moved, or deleted.']),
    (re.compile(r'^Tutler (.*?)\n本地 PC 游戏管理器\n\n数据库：\n(.*?)\n\n游戏文件不会被复制、移动或删除。$', re.S), ['Tutler ', ('GROUP', 1), '\nLocal PC game manager\n\nDatabase:\n', ('GROUP', 2), '\n\nGame files are never copied, moved, or deleted.']),
    (re.compile(r'^当前版本：(.*?)$'), ['Version: ', ('GROUP', 1)]),
])

def _tr(value):
    if not isinstance(value, str) or CURRENT_LANGUAGE != "en_US":
        return value
    direct = _TRANSLATIONS.get(value)
    if direct is not None:
        return direct
    for pattern, parts in _TRANSLATION_PATTERNS:
        match = pattern.match(value)
        if match:
            out = []
            # Pattern parts deliberately mix literal strings and capture markers.
            # Only tuples of the form ("GROUP", group_index) refer to regex groups.
            for item in parts:
                if isinstance(item, tuple) and len(item) == 2 and item[0] == "GROUP":
                    out.append(match.group(item[1]))
                else:
                    out.append(str(item))
            return "".join(out)
    return value

def _patch_text_constructor(cls, arg_index=0):
    original = cls.__init__
    def wrapped(self, *args, **kwargs):
        args = list(args)
        if len(args) > arg_index and isinstance(args[arg_index], str):
            args[arg_index] = _tr(args[arg_index])
        for key in ("text", "title", "caption"):
            if key in kwargs and isinstance(kwargs[key], str):
                kwargs[key] = _tr(kwargs[key])
        original(self, *args, **kwargs)
    cls.__init__ = wrapped

def _patch_setter(cls, method_name):
    original = getattr(cls, method_name, None)
    if original is None:
        return
    def wrapped(self, value, *args, **kwargs):
        if isinstance(value, str):
            value = _tr(value)
        return original(self, value, *args, **kwargs)
    setattr(cls, method_name, wrapped)

# Translate common visible text at creation time and for later updates.
for _cls in (QLabel, QPushButton, QCheckBox):
    _patch_text_constructor(_cls, 0)
for _cls in (QLabel, QPushButton, QCheckBox):
    _patch_setter(_cls, "setText")
_patch_setter(QLineEdit, "setPlaceholderText")
_patch_setter(QWidget, "setWindowTitle")
_patch_setter(QAction, "setText")
_patch_setter(QAction, "setToolTip")
_original_tab_add = QTabWidget.addTab
def _translated_tab_add(self, widget, *args):
    args = list(args)
    if args and isinstance(args[0], str):
        args[0] = _tr(args[0])
    return _original_tab_add(self, widget, *args)
QTabWidget.addTab = _translated_tab_add
_original_add_item = QComboBox.addItem
def _translated_add_item(self, text, userData=None):
    return _original_add_item(self, _tr(text) if isinstance(text, str) else text, userData)
QComboBox.addItem = _translated_add_item
_original_add_items = QComboBox.addItems
def _translated_add_items(self, texts):
    return _original_add_items(self, [_tr(x) if isinstance(x, str) else x for x in texts])
QComboBox.addItems = _translated_add_items
# QFileDialog static methods do not pass through QWidget.setWindowTitle, so translate
# their caption and file-filter arguments explicitly.
for _dialog_method in ("getOpenFileName", "getSaveFileName", "getOpenFileNames"):
    _original_file_dialog = getattr(QFileDialog, _dialog_method)
    def _make_file_dialog_wrapper(original):
        def _wrapped(*args, **kwargs):
            args = list(args)
            if len(args) > 1 and isinstance(args[1], str):
                args[1] = _tr(args[1])
            if len(args) > 3 and isinstance(args[3], str):
                args[3] = _tr(args[3])
            for key in ("caption", "filter"):
                if key in kwargs and isinstance(kwargs[key], str):
                    kwargs[key] = _tr(kwargs[key])
            return original(*args, **kwargs)
        return _wrapped
    setattr(QFileDialog, _dialog_method, staticmethod(_make_file_dialog_wrapper(_original_file_dialog)))

for _method_name in ("warning", "information", "critical", "question", "about"):
    _original_msg = getattr(QMessageBox, _method_name)
    def _make_msg_wrapper(original):
        def _wrapped(*args, **kwargs):
            args = list(args)
            # QMessageBox static helpers use (parent, title, text, ...).
            if len(args) > 1 and isinstance(args[1], str): args[1] = _tr(args[1])
            if len(args) > 2 and isinstance(args[2], str): args[2] = _tr(args[2])
            return original(*args, **kwargs)
        return _wrapped
    setattr(QMessageBox, _method_name, staticmethod(_make_msg_wrapper(_original_msg)))
# Translate static-dialog arguments too; Qt creates these dialogs internally.
_original_input_get_text = QInputDialog.getText
def _translated_input_get_text(*args, **kwargs):
    args = list(args)
    # getText(parent, title, label, ...)
    if len(args) > 1 and isinstance(args[1], str):
        args[1] = _tr(args[1])
    if len(args) > 2 and isinstance(args[2], str):
        args[2] = _tr(args[2])
    return _original_input_get_text(*args, **kwargs)
QInputDialog.getText = staticmethod(_translated_input_get_text)

for _method_name in ("setText", "setInformativeText", "setDetailedText"):
    _patch_setter(QMessageBox, _method_name)
    
# --- QFormLayout / QDialogButtonBox 可见文本翻译 ---------------------------------
# QFormLayout.addRow(str, widget) 会在 C++ 内部创建 QLabel，不经过 Python 的
# QLabel.__init__ patch，所以必须单独拦截 addRow/insertRow 的字符串标签参数。
_original_form_add_row = QFormLayout.addRow

def _translated_form_add_row(self, *args, **kwargs):
    args = list(args)
    # addRow(labelText: str, field)  /  addRow(labelText: str)
    if args and isinstance(args[0], str):
        args[0] = _tr(args[0])
    return _original_form_add_row(self, *args, **kwargs)

QFormLayout.addRow = _translated_form_add_row

_original_form_insert_row = QFormLayout.insertRow

def _translated_form_insert_row(self, *args, **kwargs):
    args = list(args)
    # insertRow(row, labelText: str, field)  /  insertRow(row, labelText: str)
    if len(args) >= 2 and isinstance(args[1], str):
        args[1] = _tr(args[1])
    return _original_form_insert_row(self, *args, **kwargs)

QFormLayout.insertRow = _translated_form_insert_row

# QDialogButtonBox 的标准按钮文本由 Qt 原生 locale 决定，不经过 setText patch。
# 这里在构造和 setStandardButtons 之后统一改写为当前 UI 语言，保证与
# _show_message / _confirm_action 手动创建的中文按钮风格一致。
_DBB_STANDARD_TEXTS = {
    QDialogButtonBox.StandardButton.Ok:             ("确定", "OK"),
    QDialogButtonBox.StandardButton.Cancel:         ("取消", "Cancel"),
    QDialogButtonBox.StandardButton.Save:           ("保存", "Save"),
    QDialogButtonBox.StandardButton.Close:          ("关闭", "Close"),
    QDialogButtonBox.StandardButton.Yes:            ("是",   "Yes"),
    QDialogButtonBox.StandardButton.No:             ("否",   "No"),
    QDialogButtonBox.StandardButton.Open:           ("打开", "Open"),
    QDialogButtonBox.StandardButton.Discard:        ("放弃", "Discard"),
    QDialogButtonBox.StandardButton.Apply:          ("应用", "Apply"),
    QDialogButtonBox.StandardButton.Reset:          ("重置", "Reset"),
    QDialogButtonBox.StandardButton.RestoreDefaults: ("恢复默认", "Restore Defaults"),
}

def _apply_dbb_texts(button_box):
    index = 1 if CURRENT_LANGUAGE == "en_US" else 0
    for standard, texts in _DBB_STANDARD_TEXTS.items():
        button = button_box.button(standard)
        if button is not None:
            button.setText(texts[index])

_original_dbb_init = QDialogButtonBox.__init__

def _translated_dbb_init(self, *args, **kwargs):
    _original_dbb_init(self, *args, **kwargs)
    _apply_dbb_texts(self)

QDialogButtonBox.__init__ = _translated_dbb_init

_original_set_standard_buttons = QDialogButtonBox.setStandardButtons

def _translated_set_standard_buttons(self, buttons):
    _original_set_standard_buttons(self, buttons)
    _apply_dbb_texts(self)

QDialogButtonBox.setStandardButtons = _translated_set_standard_buttons
# --- end QFormLayout / QDialogButtonBox ---
# CSV dialogs and concise navigation labels (keep English labels within the sidebar width).
_TRANSLATIONS.update({
    "导入游戏清单": "Import Game List",
    "导出游戏清单": "Export Game List",
    "CSV 文件 (*.csv)": "CSV files (*.csv)",
    "CSV 至少需要包含 name 和 exe_path 两列。": "The CSV must contain the name and exe_path columns.",
    "导入完成": "Import Complete",
    "导出成功": "Export Successful",
    "导出失败": "Export Failed",
    "导入失败": "Import Failed",
    "导入 CSV 清单": "Import CSV",
    "导出 CSV 清单": "Export CSV",
    "＋  自定义分类": "+  Add Category",
    "↕  排序/管理游戏分类": "↕  Manage Categories",
    "＋  自定义视频分类": "+  Add Category",
    "↕  排序/管理视频分类": "↕  Manage Categories",
    "＋  自定义图片分类": "+  Add Category",
    "↕  排序/管理图片分类": "↕  Manage Categories",
    "⚙    应用设置": "⚙    Settings",
    "本机数据 · 离线可用": "Local · Offline-ready",
    "管理并启动你电脑上的游戏": "Manage and launch PC games",
    "知道了": "OK",
    "导入游戏清单": "Import Game List",
    "管理并启动你电脑上的游戏": "Manage and launch PC games",
})

# --- end bilingual UI layer ---

def set_language(language):
    """Set the active UI language. Supported values: zh_CN and en_US."""
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = language if language in {"zh_CN", "en_US"} else "zh_CN"

