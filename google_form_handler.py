import time
from seleniumbase import SB

class FormFiller:
    def __init__(self, headless=False):
        self.headless = headless

    def fill_form(self, url: str, data: dict):
        """
        使用 SeleniumBase 填写表单
        data: 结构化简历数据，例如 {'name': '张三', 'email': 'zhangsan@example.com', ...}
        """
        with SB(uc=True, headless=self.headless) as sb:
            sb.open(url)
            sb.maximize_window()
            time.sleep(2)  # 等待页面加载

            # 这是一个通用的映射尝试，实际生产中需要根据目标表单的 Selector 进行调整
            # 为了 Demo 演示，我们假设目标表单有标准的 name 或 placeholder 属性
            
            # 填写姓名
            if 'name' in data and data['name']:
                self._safe_fill(sb, "姓名", data['name'])
            
            # 填写邮箱
            if 'email' in data and data['email']:
                self._safe_fill(sb, "邮箱", data['email'])
            
            # 填写电话
            if 'phone' in data and data['phone']:
                self._safe_fill(sb, "电话", data['phone'])

            # 填写教育背景
            if 'education' in data and data['education']:
                self._safe_fill(sb, "教育", str(data['education']))

            # 填写工作经历
            if 'experience' in data and data['experience']:
                self._safe_fill(sb, "工作", str(data['experience']))

            # 填写技能
            if 'skills' in data and data['skills']:
                self._safe_fill(sb, "技能", str(data['skills']))

            sb.highlight("body") # 视觉高亮提示已完成
            time.sleep(5)  # 留出时间给用户观察
            # sb.click('button[type="submit"]') # 默认不点击提交，让用户核对

    def _safe_fill(self, sb, label_hint: str, value: str):
        """尝试通过多种选择器定位并填写输入框"""
        try:
            # 尝试通过 label 文本定位附近的 input
            # 这是针对简单表单的启发式方法
            selectors = [
                f"input[placeholder*='{label_hint}']",
                f"input[name*='{label_hint.lower()}']",
                f"input[id*='{label_hint.lower()}']",
                f"textarea[placeholder*='{label_hint}']",
                f"//label[contains(text(), '{label_hint}')]/following::input[1]",
                f"//div[contains(text(), '{label_hint}')]/following::input[1]"
            ]
            
            for selector in selectors:
                if sb.is_element_visible(selector):
                    sb.type(selector, value)
                    sb.highlight(selector)
                    return True
            return False
        except Exception as e:
            print(f"填写 {label_hint} 时出错: {e}")
            return False

# 如果是为了 Demo 演示，我们可以创建一个本地 HTML
def create_demo_html(file_path: str = "demo_form.html"):
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>求职申请模拟表单</title>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #f4f7f6; }
            .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            h2 { color: #333; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; color: #666; }
            input, textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            button { background: #5cb85c; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>求职申请表 (Demo)</h2>
            <div class="form-group">
                <label>姓名</label>
                <input type="text" id="name" placeholder="请输入姓名">
            </div>
            <div class="form-group">
                <label>邮箱</label>
                <input type="email" id="email" placeholder="请输入邮箱">
            </div>
            <div class="form-group">
                <label>电话</label>
                <input type="text" id="phone" placeholder="请输入电话">
            </div>
            <div class="form-group">
                <label>教育经历</label>
                <textarea id="education" placeholder="请输入教育经历"></textarea>
            </div>
            <div class="form-group">
                <label>工作经历</label>
                <textarea id="experience" placeholder="请输入工作经历"></textarea>
            </div>
            <div class="form-group">
                <label>技能</label>
                <input type="text" id="skills" placeholder="请输入技能">
            </div>
            <button onclick="alert('提交成功！')">提交申请</button>
        </div>
    </body>
    </html>
    """
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(file_path)
