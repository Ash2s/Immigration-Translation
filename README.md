# Immigration Translation Web

中译英移民文档翻译工具。上传 .docx 文件 + 术语表，通过 DeepSeek API 自动翻译并保留原文格式。

## 功能

- **文档翻译** — 上传 .docx 文件，自动识别正文/表格/文本框并翻译
- **术语表** — 上传 CSV/XLSX 术语表，保证专业词汇翻译一致性
- **格式保留** — 翻译后保留字体、颜色、行距、加粗/斜体等格式
- **格式修正** — 翻译完成后可针对性地修改段落格式（颜色、行距、字体等）
- **内容修正** — 翻译完成后可提交反馈重新翻译，修正指令不会出现在输出中
- **预览 & 下载** — 在线预览翻译结果，下载 .docx 文件

## 技术栈

- **后端**: FastAPI + python-docx + DeepSeek API (OpenAI 兼容接口)
- **前端**: 原生 HTML/CSS/JS
- **依赖**: 见 requirements.txt

## 使用

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量 (`.env`)：
   ```
   DEEPSEEK_API_KEY=your_key_here
   DEEPSEEK_MODEL=deepseek-chat
   GLOSSARY_DIR=/tmp/glossaries
   UPLOAD_DIR=/tmp/uploads
   ```

3. 启动服务：
   ```bash
   uvicorn main:app --reload
   ```

4. 打开浏览器访问 `http://localhost:8000`

## 项目结构

```
├── app/
│   ├── api/routes.py          # API 路由
│   ├── services/
│   │   ├── document_parser.py # .docx 解析与格式操作
│   │   ├── glossary.py        # 术语表管理
│   │   └── translator.py      # DeepSeek 翻译服务
│   ├── models/schemas.py      # Pydantic 数据模型
│   └── config.py              # 配置
├── static/index.html          # 前端界面
├── main.py                    # 入口
└── requirements.txt
```
