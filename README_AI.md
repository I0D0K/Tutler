# Tutler AI integration / Tutler AI 功能

## 中文

本版本在原有 Tutler 启动器上添加了圆形悬浮 AI 按钮。点击按钮后会打开独立聊天面板，面板主题会跟随启动器的深色/亮色设置，界面文字支持中文和英文。

AI 模块独立放在 `ai_assistant.py`，`main.py` 只负责把它接入启动器、查询本地数据库，并验证游戏启动请求。

支持的功能：
- 普通聊天与问答。
- 查询游戏库、按游戏名/分类/标签搜索游戏、查看收藏和最近游玩的游戏。
- 按明确的“启动/打开/玩 + 游戏名称”指令启动已收录的游戏。启动前会和本地数据库中的名称匹配，不会根据模型输出执行任意命令或任意路径。
- 将指定游戏分类：例如“把《黑神话：悟空》分类为 RPG”。分类代码会校验，游戏名称必须与本地库准确匹配。
- 自动分类：AI 根据游戏名称和已有信息为游戏库生成分类建议，先展示待修改清单，用户确认后才批量写入。
- 删除已录入的游戏：例如“删除《黑神话：悟空》”。必须准确匹配游戏名称，并弹出 Tutler 原有的移除确认框；只删除游戏库记录，不会删除磁盘上的游戏文件。
- 点击聊天窗标题栏的齿轮按钮，可选择 OpenAI-compatible local inference server、DeepSeek 或通义千问 Qwen。DeepSeek/Qwen 的 API 地址由程序自动设置，用户只需选择模型并填写对应 API Key；模型选择和配置会保存，下次提问无需重复选择。
- 聊天窗使用不透明背景，避免在 Windows 上出现异常透明区域。

### 安装与运行

1. 将 `main.py`、`i18n.py`、`ai_assistant.py` 放在同一个项目目录。
2. 在该目录打开终端，安装 Python 依赖：

   ```bat
   python -m pip install -r requirements.txt
   ```

3. 安装并启动 LM Studio, Ollama, or another local inference server exposing an OpenAI-compatible API，然后下载测试模型：

   ```bat
   OpenAI-compatible local inference server pull qwen3.5:4b
   ```

4. 启动 Tutler：

   ```bat
   python main.py
   ```

如果 OpenAI-compatible local inference server 没有运行或模型尚未下载，AI 面板会显示对应提示；Tutler 的原有游戏管理功能仍可打开和使用。

## English

This integration adds a circular floating AI button to Tutler. Clicking it opens a separate chat panel whose colors follow the launcher's light/dark theme. The assistant UI supports Chinese and English.

The AI UI and model worker live in `ai_assistant.py`. `main.py` only integrates the assistant with the launcher, queries the local game database, and validates launch requests.

Features:
- General chat and Q&A.
- List the game library and search by title, category, or tag; view favorites and recently played games.
- Launch a game already stored in Tutler when the user explicitly asks to launch/open/play it by name. Game names are checked against the local database; model output is never used to execute arbitrary commands or paths.
- Assign a category to a specified game (for example, “Set Black Myth: Wukong to RPG”), with category validation and strict local title matching.
- Automatically categorize the library: AI proposes category assignments, previews the changes, and only updates the database after confirmation.
- Remove a registered game by title. Tutler requires an exact match and shows its existing confirmation dialog; only the library record is removed, never the game files.
- Click the gear button in the chat header to choose OpenAI-compatible local inference server, DeepSeek, or Qwen. DeepSeek/Qwen endpoints are predefined, so users only select a model and enter the relevant API key. The selection is saved and does not need to be repeated for every message.
- The chat window uses an opaque background to avoid unexpected transparency on Windows.

### Install and run

1. Keep `main.py`, `i18n.py`, and `ai_assistant.py` in the same project directory.
2. Install Python dependencies in that directory:

   ```bat
   python -m pip install -r requirements.txt
   ```

3. Install and start LM Studio, Ollama, or another local inference server exposing an OpenAI-compatible API, then download a model in that application. For LM Studio, load a model and start its local server (commonly `http://localhost:1234/v1`). For Ollama, start Ollama and use its OpenAI-compatible endpoint (commonly `http://localhost:11434/v1`).

4. Start Tutler:

   ```bat
   python main.py
   ```

The default model is `qwen3.5:4b`. If OpenAI-compatible local inference server is not running or the model is missing, the AI panel displays a setup hint. Tutler's existing game-management features remain available.

To use an API, click the gear in the chat header, choose DeepSeek or Qwen, select a model, enter the API key, and select “Save & switch”. The official endpoint is selected automatically. The API key is stored in Tutler local settings; do not save personal credentials on shared Windows accounts or untrusted devices.


### Supported model providers

- Local model: enter an OpenAI-compatible endpoint, for example `http://localhost:1234/v1`. Tutler no longer uses the Ollama integration package.
- OpenAI, DeepSeek, and Qwen: use their built-in official endpoints; enter the matching API key and model name.
- Other compatible model: enter the endpoint, model name, and API key if the service requires one.

The local inference server must expose an OpenAI-compatible Chat Completions API. A raw model file path is not an API endpoint.
