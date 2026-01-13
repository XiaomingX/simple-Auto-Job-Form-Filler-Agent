# Skill: Implementation Details for Auto-Filler

## 1. Project Initialization (uv)
使用以下命令初始化项目并安装依赖：
```bash
# 1. 初始化
uv init job-filler
cd job-filler

# 2. 添加核心依赖
uv add chainlit langchain langchain-openai seleniumbase pypdf python-docx

# 3. 安装 seleniumbase 浏览器内核
uv run seleniumbase install chromium