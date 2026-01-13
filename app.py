import os
import chainlit as cl
from resume_processor import ResumeProcessor
from google_form_handler import FormFiller, create_demo_html

# 初始化处理器
# 注意：实际使用时建议通过环境变量或 UI 输入获取 API KEY
processor = ResumeProcessor(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
)
filler = FormFiller(headless=False)

@cl.on_chat_start
async def start():
    assets_dir = "assets"
    files = []
    if os.path.exists(assets_dir):
        files = [f for f in os.listdir(assets_dir) if f.endswith(('.pdf', '.docx', '.txt'))]
    
    welcome_msg = "👋 您好！我是 AI 求职助手。您可以上传您的简历（PDF, Word 或 TXT），或者直接从 assets 目录中选择一个文件（输入文件名即可）。"
    if files:
        welcome_msg += f"\n\n当前 assets 目录中的可选简历：\n" + "\n".join([f"- `{f}`" for f in files])
    
    await cl.Message(content=welcome_msg).send()
    
    # 询问用户是否需要使用 Demo 表单
    demo_path = create_demo_html()
    cl.user_session.set("demo_url", f"file://{demo_path}")

async def process_resume(file_path, file_name):
    msg = cl.Message(content=f"正在解析简历: {file_name}...")
    await msg.send()
    
    try:
        # 1. 解析简历
        data = processor.process(file_path)
        cl.user_session.set("resume_data", data)
        
        # 展示解析结果
        await cl.Message(content=f"✅ 解析完成！以下是提取的信息：\n```json\n{data}\n```" ).send()
        
        # 2. 引导填表
        res = await cl.AskUserMessage(content="请输入目标表单的 URL（直接回复 'demo' 使用本地演示页面）：", timeout=60).send()
        
        if res:
            target_url = res['output']
            if target_url.lower() == 'demo':
                target_url = cl.user_session.get("demo_url")
            
            await cl.Message(content=f"🚀 正在启动浏览器自动填写: {target_url}").send()
            
            # 3. 执行填表 (同步转异步处理)
            await cl.make_async(filler.fill_form)(target_url, data)
            
            await cl.Message(content="🎊 填写完成！请在浏览器窗口查看结果。" ).send()
            
    except Exception as e:
        await cl.Message(content=f"❌ 处理过程中出错: {str(e)}").send()

@cl.on_message
async def main(message: cl.Message):
    # 检查是否输入的是 assets 目录下的文件名
    assets_dir = "assets"
    file_path = os.path.join(assets_dir, message.content.strip())
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        await process_resume(file_path, message.content.strip())
    else:
        await cl.Message(content="未找到该文件，请上传简历或输入 assets 目录下的正确文件名。").send()

@cl.on_file_upload(accept=["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"])
async def handle_file(files):
    file = files[0]
    # 保存临时文件
    temp_path = f"temp_{file.name}"
    with open(temp_path, "wb") as f:
        f.write(file.content)
    
    await process_resume(temp_path, file.name)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)

if __name__ == "__main__":
    # 提醒用户如何运行
    print("请使用以下命令启动应用: chainlit run app.py")
