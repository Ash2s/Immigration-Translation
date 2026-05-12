# Immigration Translation Web

中译英移民文档翻译工具。上传 .docx 文件 + 术语表，通过 DeepSeek API（或其他 OpenAI 兼容接口）自动翻译并保留原文格式。

## 功能

- **文档翻译** — 上传 .docx 文件，自动识别正文/表格/文本框并翻译
- **术语表** — 上传 CSV/XLSX 术语表，保证专业词汇翻译一致性
- **自定义 API** — 支持使用自己的 API Key / Base URL / 模型，不限 DeepSeek
- **格式保留** — 翻译后保留字体、颜色、行距、加粗/斜体等格式
- **内容修正** — 翻译完成后可提交反馈重新翻译，修正指令不会出现在输出中
- **实时进度** — 可视化进度环 + 逐文件状态跟踪
- **批量下载** — 多文件翻译结果一键打包 ZIP 下载
- **预览 & 下载** — 在线预览翻译结果，下载 .docx 文件

## 技术栈

- **后端**: FastAPI + python-docx + DeepSeek API (OpenAI 兼容接口)
- **前端**: 原生 HTML/CSS/JS（无框架依赖）
- **依赖**: 见 requirements.txt

## 使用

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量 (`.env`)：
   ```
   DEEPSEEK_API_KEY=your_key_here
   DEEPSEEK_MODEL=deepseek-v4-flash
   GLOSSARY_DIR=/tmp/glossaries
   UPLOAD_DIR=/tmp/uploads
   ```

3. 启动服务：
   ```bash
   python main.py
   ```

4. 打开浏览器访问 `http://localhost:8000`

> 如果使用自己的 API Key，可在界面中展开「自定义 API」面板填写，无需修改服务器配置。

## 项目结构

```
├── app/
│   ├── api/routes.py          # API 路由 & 后台翻译任务
│   ├── services/
│   │   ├── document_parser.py # .docx 解析与格式操作
│   │   ├── glossary.py        # 术语表管理
│   │   └── translator.py      # DeepSeek 翻译服务
│   ├── models/schemas.py      # Pydantic 数据模型
│   └── config.py              # 配置
├── static/index.html          # 前端界面（单页应用）
├── main.py                    # 入口
└── requirements.txt
```
