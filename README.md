# AI 自动求职投递助手 🤖

本项目是一个基于 AI 的自动化工具，旨在根据您的简历信息自动填写求职申请表（如 Google Forms 等）。它利用大语言模型（LLM）解析简历，并结合 SeleniumBase 实现浏览器的自动化填写。

## 核心功能

- **简历智能解析**：使用 LLM 自动从 PDF 或 Word 简历中提取姓名、邮箱、电话、教育背景、工作经历及技能等关键信息。
- **自动化表单填写**：基于 SeleniumBase 智能定位表单字段，并将解析出的简历数据准确填入。
- **交互式界面**：基于 Chainlit 构建的友好聊天界面，方便用户上传文件和核对信息。
- **演示模式**：提供本地 HTML 模拟表单，可用于快速测试自动化填写效果。

## 文件结构

- `app.py`: 应用主入口（基于 Chainlit）。
- `resume_processor.py`: 处理简历文本提取与 LLM 解析。
- `google_form_handler.py`: 封装浏览器自动化填写逻辑及 Demo 表单生成。
- `requirements.txt`: 项目依赖列表。

## 安装与使用

1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

2. **安装浏览器驱动**:
   ```bash
   seleniumbase install chromium
   ```

3. **配置环境变量**:
   设置您的 OpenAI API 密钥：
   ```bash
   export OPENAI_API_KEY='your-api-key'
   # 如果使用代理或其它兼容 API
   export OPENAI_API_BASE='https://api.your-proxy.com/v1'
   ```

4. **启动应用**:
   ```bash
   chainlit run app.py
   ```

5. **使用步骤**:
   - 上传您的简历文件（PDF 或 DOCX）。
   - 等待 AI 解析完成并核对提取的信息。
   - 输入目标表单 URL（或输入 `demo` 使用本地测试页面）。
   - 观察浏览器自动完成填表过程。

## 开源协议

MIT License