import json
import requests
import re
import pandas as pd

class GoogleFormHandler:
    ALL_DATA_FIELDS = "FB_PUBLIC_LOAD_DATA_"  # 谷歌表单中存储所有数据的变量名
    FORM_SESSION_TYPE_ID = 8  # 表单分页类型对应的ID
    ANY_TEXT_FIELD = "ANY TEXT!!"  # 通用文本字段标识
    
    def __init__(self, url: str):
        self.url = url  # 谷歌表单的原始URL
        self.form_data = None  # 存储从表单提取的原始数据
        self.entries = None  # 存储解析后的表单字段列表
        self.page_count = 0  # 表单的分页数
        
    def _get_form_response_url(self):
        ''' 将表单查看URL转换为表单提交响应URL '''
        # 替换URL中的"/viewform"为"/formResponse"（谷歌表单提交接口路径）
        url = self.url.replace('/viewform', '/formResponse')
        # 若URL末尾未包含"/formResponse"，则补充完整路径
        if not url.endswith('/formResponse'):
            if not url.endswith('/'):
                url += '/'
            url += 'formResponse'
        return url

    def _extract_script_variables(self, name: str, html: str):
        """ 从HTML页面的script标签中提取指定名称的变量 """
        # 正则表达式：匹配"var 变量名 = 变量值;"的格式
        pattern = re.compile(r'var\s' + name + r'\s=\s(.*?);')
        match = pattern.search(html)
        if not match:
            return None
        # 获取变量值的字符串形式，并转换为JSON格式（便于解析）
        value_str = match.group(1)
        return json.loads(value_str)

    def _get_fb_public_load_data(self):
        """ 从谷歌表单URL中获取表单的核心数据（FB_PUBLIC_LOAD_DATA_变量） """
        # 发送GET请求获取表单页面内容，超时时间设为10秒
        response = requests.get(self.url, timeout=10)
        # 若请求状态码不是200（成功），打印错误信息并返回None
        if response.status_code != 200:
            print("错误！无法获取表单数据，状态码：", response.status_code)
            return None
        # 从页面HTML中提取FB_PUBLIC_LOAD_DATA_变量的数据
        return self._extract_script_variables(self.ALL_DATA_FIELDS, response.text)

    def _parse_entry(self, entry):
        """ 解析单个表单字段组，提取其中的子字段信息 """
        entry_name = entry[1]  # 字段组名称（如"个人信息"）
        entry_type_id = entry[3]  # 字段组的类型ID
        result = []  # 存储解析后的子字段列表
        
        # 遍历字段组中的每个子字段
        for sub_entry in entry[4]:
            info = {
                "id": sub_entry[0],  # 子字段的唯一ID
                "container_name": entry_name,  # 所属字段组名称
                "type": entry_type_id,  # 子字段类型ID
                "required": sub_entry[2] == 1,  # 是否为必填字段（1表示必填）
                # 子字段名称（若存在多层名称则用" - "连接）
                "name": ' - '.join(sub_entry[3]) if (len(sub_entry) > 3 and sub_entry[3]) else None,
                # 子字段的可选选项（若存在选项则提取，通用文本字段用ANY_TEXT_FIELD标识）
                "options": [(x[0] or self.ANY_TEXT_FIELD) for x in sub_entry[1]] if sub_entry[1] else None,
            }
            result.append(info)
        return result

    def parse_form_entries(self):
        """ 解析表单的所有字段，返回完整的字段列表 """
        # 获取表单提交接口的URL
        url = self._get_form_response_url()
        # 从表单页面提取核心数据
        self.form_data = self._get_fb_public_load_data()

        # 若核心数据不存在或格式异常，打印错误信息（可能需要登录权限）
        if not self.form_data or not self.form_data[1] or not self.form_data[1][1]:
            print("错误！无法获取表单字段，可能需要登录权限。")
            return None
        
        parsed_entries = []  # 存储所有解析后的字段
        self.page_count = 0  # 重置分页数
        
        # 遍历表单核心数据中的字段组
        for entry in self.form_data[1][1]:
            # 若字段组是分页类型（TYPE_ID=8），分页数加1并跳过解析
            if entry[3] == self.FORM_SESSION_TYPE_ID:
                self.page_count += 1
                continue
            # 解析当前字段组的子字段，并添加到总列表中
            parsed_entries += self._parse_entry(entry)

        # 若表单要求收集邮箱，添加邮箱字段信息
        if self.form_data[1][10][6] > 1:
            parsed_entries.append({
                "id": "emailAddress",  # 邮箱字段标识
                "container_name": "Email Address",  # 字段名称（邮箱地址）
                "type": "required",  # 字段类型（必填）
                "required": True,  # 是否必填（是）
                "options": "email address",  # 选项说明（邮箱格式）
            })
        
        # 若表单有分页，添加分页历史字段（用于记录分页导航）
        if self.page_count > 0:
            parsed_entries.append({
                "id": "pageHistory",  # 分页历史字段标识
                "container_name": "Page History",  # 字段名称（分页历史）
                "type": "required",  # 字段类型（必填，用于表单提交验证）
                "required": False,  # 实际无需用户填写
                "options": "from 0 to (number of page - 1)",  # 选项说明（分页范围）
                "default_value": ','.join(map(str, range(self.page_count + 1)))  # 默认值（分页索引拼接）
            })
        
        # 保存解析后的字段列表，并返回
        self.entries = parsed_entries
        return parsed_entries

    def get_form_questions_df(self, only_required=False) -> pd.DataFrame:
        """
        将表单问题转换为pandas DataFrame格式，便于查看和处理。
        
        返回：
            DataFrame对象，包含以下列：
                Entry_ID: 字段唯一ID（格式为"entry.字段ID"）
                Question: 问题描述（含字段组名称和子字段名称）
                Required: 是否必填（布尔值）
                Field_Type: 字段类型（如短答案、单选题等）
                Selection_Type: 选择类型（如单选、下拉、多选，仅适用于选择类字段）
                Options: 可选选项（多个选项用逗号分隔，无选项则为None）
        """
        # 若未解析过字段，先执行解析
        if not self.entries:
            self.parse_form_entries()
            
        # 若解析后仍无字段数据，返回空DataFrame
        if not self.entries:
            return pd.DataFrame()
            
        questions_data = []  # 存储问题数据的列表
        
        # 遍历每个解析后的字段，构造DataFrame的行数据
        for entry in self.entries:
            # 基础问题描述（字段组名称）
            question_text = entry['container_name']
            # 若有子字段名称，补充到问题描述中（如"个人信息：姓名"）
            if entry.get('name'):
                question_text += f": {entry['name']}"
                
            # 确定选择类字段的选择类型（仅适用于特定类型ID）
            selection_type = None
            if entry['type'] in [2, 3, 4]:  # 2=单选题，3=下拉选择，4=多选题
                if entry['type'] == 2:
                    selection_type = "Single Choice"  # 单选题（保持英文便于后续逻辑兼容）
                elif entry['type'] == 3:
                    selection_type = "Dropdown"  # 下拉选择（保持英文便于后续逻辑兼容）
                elif entry['type'] == 4:
                    selection_type = "Multiple Choice"  # 多选题（保持英文便于后续逻辑兼容）
                
            # 构造单行问题数据
            question_info = {
                # 字段ID：普通字段格式为"entry.字段ID"，特殊字段（如邮箱）直接用ID
                'Entry_ID': f"entry.{entry['id']}" if entry.get('type') != "required" else entry['id'],
                'Question': question_text,  # 问题描述
                'Required': entry['required'],  # 是否必填
                'Field_Type': self.get_form_type_value_rule(entry['type']),  # 字段类型（中文说明）
                'Selection_Type': selection_type,  # 选择类型（仅选择类字段有值）
                # 选项：多个选项用逗号拼接，无选项则为None
                'Options': ', '.join(entry['options']) if entry.get('options') else None
            }
            questions_data.append(question_info)
        
        # 转换为DataFrame，并过滤掉分页历史字段（无需展示给用户）
        questions_df = pd.DataFrame(questions_data)
        questions_df = questions_df[questions_df["Entry_ID"] != "pageHistory"]
        
        # 若仅需返回必填字段，过滤掉非必填项
        if only_required:
            questions_df = questions_df[questions_df["Required"] == True]
            
        return questions_df

    def get_form_type_value_rule(self, type_id):
        ''' 
        根据字段类型ID，返回对应的字段类型中文说明。
        ------ 类型ID与字段类型对应关系 ------ 
            0: 短答案（Short answer）
            1: 段落（Paragraph）
            2: 单选题（Multiple choice）
            3: 下拉选择（Dropdown）
            4: 多选题（Checkboxes）
            5: 线性量表（Linear scale）
            7: 网格选择（Grid choice）
            9: 日期（Date）
            10: 时间（Time）
        '''
        # 类型ID与中文说明的映射字典
        type_mapping = {
            0: "短答案",
            1: "段落",
            2: "单选题",
            3: "下拉选择",
            4: "多选题",
            5: "线性量表",
            7: "网格选择",
            9: "日期",
            10: "时间",
            "required": "必填字段"  # 特殊类型（如邮箱）
        }
        # 若类型ID未匹配到，返回默认值"通用文本"
        return type_mapping.get(type_id, "通用文本")
    
    def fill_form_entries(self, fill_algorithm):
        """ 使用提供的填充算法，为表单字段生成默认填充值 """
        # 遍历每个表单字段
        for entry in self.entries:
            # 若字段已有默认值（如分页历史），跳过填充
            if entry.get('default_value'):
                continue
            
            # 复制字段的可选选项，并移除通用文本标识（避免算法误选）
            options = (entry['options'] or [])[::]
            if self.ANY_TEXT_FIELD in options:
                options.remove(self.ANY_TEXT_FIELD)
            
            # 调用填充算法，为当前字段生成默认值
            entry['default_value'] = fill_algorithm(
                entry['type'],  # 字段类型ID
                entry['id'],    # 字段ID
                options,        # 字段可选选项
                required=entry['required'],  # 是否必填
                entry_name=entry['container_name']  # 字段所属组名称
            )
        # 返回填充后的字段列表
        return self.entries

    def get_form_submit_request(self, output="console", only_required=False, with_comment=True, fill_algorithm=None):
        ''' 获取表单提交请求的请求体数据（用于后续提交表单） '''
        # 若未解析字段，先解析（可选择仅解析必填字段）
        if not self.entries:
            self.parse_form_entries(only_required=only_required)

        # 若提供了填充算法，先为字段生成默认值
        if fill_algorithm:
            self.entries = self.fill_form_entries(fill_algorithm)
            
        # 若解析后仍无字段数据，返回None
        if not self.entries:
            return None
        
        # 生成表单提交所需的请求体字典
        result = self.generate_form_request_dict(self.entries, with_comment)
        
        # 根据输出方式处理结果
        if output == "console":
            # 在控制台打印请求体数据
            print(result)
        elif output == "return":
            # 返回请求体数据（供后续代码使用）
            return result
        else:
            # 输出到指定文件（如JSON文件）
            with open(output, "w", encoding="utf-8") as f:
                f.write(result)
                print(f"请求体数据已保存到文件：{output}", flush=True)
            f.close()

    def submit_form(self, data):
        """ 提交表单数据到谷歌表单接口 """
        # 获取表单提交接口URL
        url = self._get_form_response_url()
        # 发送POST请求提交表单数据，超时时间5秒
        res = requests.post(url, data=data, timeout=5)
        
        # 根据响应状态码判断提交结果
        if res.status_code == 200:
            print("表单提交成功！")
            return True
        else:
            print("错误！无法提交表单，状态码：", res.status_code)
            return False


if __name__ == "__main__":
    # 示例用法（实际使用时需替换为真实表单URL和填充逻辑）
    pass