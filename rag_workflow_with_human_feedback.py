from llama_parse import LlamaParse
from llama_index.core.workflow import (
    Workflow,
    StartEvent,
    StopEvent,
    step,
    Event,
    Context
)
import os
import json
from llama_index.llms.openrouter import OpenRouter
import nest_asyncio
from resume_processor import ResumeProcessor
nest_asyncio.apply()
from llama_index.core import (
    VectorStoreIndex,
    Settings,
    StorageContext,
    load_index_from_storage,
    PromptHelper
)
from llama_index.core import StorageContext, load_index_from_storage
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from google_form_handler import GoogleFormHandler
from llama_index.core.workflow import InputRequiredEvent, HumanResponseEvent

class QueryEvent(Event):
    query: str

class ParseFormEvent(Event):
    form_data: list

class ResponseEvent(Event):
    response: str

class FeedbackEvent(Event):
    feedback: str

class RAGWorkflowWithHumanFeedback(Workflow):
    
    llm: OpenRouter
    query_engine: VectorStoreIndex

    @step
    async def set_up(self, ctx: Context, ev: StartEvent) -> ParseFormEvent:

        if not ev.resume_index_path:
            raise ValueError("需要先进行简历索引！！")
        
        if not ev.form_data:
            raise ValueError("需要表单数据！！")
            
        if not ev.openrouter_key:
            raise ValueError("需要OpenRouter API密钥！！")
            
        if not ev.llama_cloud_key:
            raise ValueError("需要Llama Cloud API密钥！！")
            
        if not ev.selected_model:
            raise ValueError("需要选择大语言模型（LLM）！！")
        
        # 配置上下文窗口及其他设置
        context_window = 4096  # 从8192缩减，提高稳定性
        num_output = 2048
        
        # 创建带有合适设置的提示助手
        prompt_helper = PromptHelper(
            context_window=context_window,
            num_output=num_output,
            chunk_overlap_ratio=0.1,  # 片段重叠比例
            chunk_size_limit=None     # 不限制片段大小
        )

        # 初始化带有合适设置的大语言模型（LLM）
        self.llm = OpenRouter(
            api_key=ev.openrouter_key,
            max_tokens=num_output,       # 最大生成token数
            context_window=context_window,  # 上下文窗口大小
            model=ev.selected_model,     # 选中的模型
            temperature=0.3,             # 随机性（0.3表示较低随机性，结果更稳定）
            top_p=0.9,                   # 采样阈值（仅保留前90%概率的token）
        )

        # 测试大语言模型（LLM）连接
        try:
            test_response = self.llm.complete("测试连接。")
            if not test_response or not test_response.text:
                raise ValueError("大语言模型（LLM）返回空响应")
        except Exception as e:
            print(f"初始化大语言模型（LLM）时出错：{str(e)}")
            raise ValueError("大语言模型（LLM）初始化失败，请检查你的API密钥和网络连接。")

        # 配置包含提示助手的服务上下文
        Settings.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-mpnet-base-v2",  # 用于生成文本嵌入的模型
            cache_folder="embeddings_cache"  # 嵌入结果缓存目录，提升性能
        )
        Settings.llm = self.llm
        Settings.prompt_helper = prompt_helper
        service_context = Settings

        # 若简历索引目录已存在，从目录加载索引
        if os.path.exists(ev.resume_index_path):
            storage_context = StorageContext.from_defaults(persist_dir=ev.resume_index_path)
            index = load_index_from_storage(
                storage_context,
                service_context=service_context
            )
        else:
            raise ValueError("未找到索引！！")

        # 配置查询引擎（优化设置）
        self.query_engine = index.as_query_engine(
            llm=self.llm,
            similarity_top_k=5,          # 仅取相似度最高的5个片段
            response_mode="tree_summarize",  # 树状总结模式，更适合结构化响应
            structured_answer_filtering=True,  # 过滤无关信息
            response_kwargs={
                "verbose": True,                # 显示详细过程
                "similarity_threshold": 0.7     # 仅使用相似度≥0.7的上下文
            }
        )

        return ParseFormEvent(form_data=ev.form_data)

    @step
    async def parse_form(self, ctx: Context, ev: ParseFormEvent | FeedbackEvent) -> QueryEvent:
        # 若为FeedbackEvent，从上下文中获取表单数据
        if isinstance(ev, FeedbackEvent):
            fields = await ctx.get("form_data")
            if not fields:
                raise ValueError("在上下文中未找到表单数据")
        else:
            fields = ev.form_data
            # 将表单数据存储到上下文中，供后续使用
            await ctx.set("form_data", fields)
        
        # 遍历所有表单字段，生成对应的查询语句
        for field in fields:
            question = field["Question"]       # 问题内容
            options = field["Options"]         # 选项（选择题时存在）
            required = field["Required"]       # 是否为必填项
            entry_id = field["Entry_ID"]       # 字段唯一ID（用于提交表单）
            selection_type = field.get("Selection_Type", "Text")  # 字段类型（默认文本框）
            
            # 根据字段类型，构建更有针对性的查询语句
            if selection_type in ["Single Choice", "Dropdown"]:
                # 单选题/下拉框：让AI从选项中选择最匹配的答案
                query = f"""根据候选人的简历，以下哪个选项最能回答该问题？
                问题ID：{entry_id}
                问题：{question}
                选项：{options}
                请根据候选人的经历和资质，选择最合适的选项。"""
            elif selection_type == "Multiple Choice":
                # 多选题：让AI选择所有匹配的选项
                query = f"""根据候选人的简历，以下哪些选项符合该问题要求？
                问题ID：{entry_id}
                问题：{question}
                选项：{options}
                请根据候选人的经历和资质，选择所有相关选项。"""
            else:
                # 文本框：让AI从简历中提取事实性答案
                query = f"""根据候选人的简历，请为以下问题提供事实性答案：
                问题ID：{entry_id}
                问题：{question}
                回答请具体、简洁。"""
            
            # 若有用户反馈，将反馈加入查询，优化AI回答
            if isinstance(ev, FeedbackEvent):
                query += f"""\n此前我们收到了关于该问题回答的反馈（可能与当前字段无关，但供参考）：
                <反馈内容>
                {ev.feedback}
                </反馈内容>
                """

            # 发送查询事件，传递查询相关信息
            ctx.send_event(QueryEvent(
                query=query,
                query_type="简历分析",
                field=question,
                entry_id=entry_id,
                required=required
            ))
        
        # 将表单总字段数存储到上下文
        await ctx.set("total_fields", len(fields))
        return
        
    @step
    async def ask_question(self, ctx: Context, ev: QueryEvent) -> ResponseEvent:

        # 构建查询提示（明确AI的任务和规则）
        query = f"""请分析以下关于候选人简历的问题，并提供详细、真实的回答。
        重点提取简历中的具体细节，保持专业语气。
        
        {ev.query}
        
        指导原则：
        1. 若简历中有相关具体细节，务必使用
        2. 若简历中无相关信息，需明确说明“简历中未找到该信息”
        3. 对于选择题，需根据简历内容解释选择理由
        """
        
        try:
            # 第一步：尝试使用查询引擎（结合简历索引，更精准）
            try:
                response = self.query_engine.query(query)
                # 检查响应是否有效
                if response and hasattr(response, 'response') and response.response:
                    response_text = response.response
                else:
                    raise ValueError("查询引擎返回空响应")
            except Exception as query_error:
                print(f"查询引擎错误：{str(query_error)}")
                # 第二步：若查询引擎失败，退而直接使用大语言模型（LLM）
                llm_response = self.llm.complete(query)
                if not llm_response or not llm_response.text:
                    raise ValueError("退用大语言模型（LLM）时返回空响应")
                response_text = llm_response.text
                
            print(f"回答结果：{response_text}")
            
            # 返回带有字段信息的响应事件
            return ResponseEvent(
                response=response_text,
                field=ev.field,
                entry_id=ev.entry_id,
                required=ev.required
            )
        except Exception as e:
            error_msg = str(e)
            print(f"ask_question方法出错：{error_msg}")
            
            # 生成错误 fallback 提示（告知用户无法处理）
            fallback_msg = (
                "目前无法处理该问题。"
                "若这是必填项，请重试或手动填写相关信息。"
            )
            
            # 若为必填项，额外标注
            if ev.required:
                fallback_msg += "（这是必填项）"
            
            return ResponseEvent(
                response=fallback_msg,
                field=ev.field,
                entry_id=ev.entry_id,
                required=ev.required
            )

    @step
    async def fill_in_application(self, ctx:Context, ev:ResponseEvent) -> InputRequiredEvent:
        # 从上下文获取表单总字段数
        total_fields = await ctx.get("total_fields")
        # 收集所有字段的回答（需收集满total_fields个ResponseEvent）
        responses = ctx.collect_events(ev, [ResponseEvent]*total_fields)
        # 从上下文获取原始表单数据
        form_data = await ctx.get("form_data")

        if responses is None:
            return None 

        # 构建结构化的回答列表（便于AI后续整理）
        responsesList = "\n".join(
            f"字段ID：{r.entry_id}\n" + 
            f"问题：{r.field}\n" + 
            f"回答：{r.response}\n" + 
            f"---" 
            for r in responses
        )        
        
        # 调用AI，将分散的回答整理为标准JSON格式（便于表单提交）
        result = self.llm.complete(f"""
            你是分析简历和填写申请表的专家。你的任务是：
            1. 审核候选人简历相关的问题与回答
            2. 为每个问题提供清晰、简洁、真实的最终答案
            指导原则：
            - 对于选择题，仅保留最相关的选项
            - 若问题无法从简历中找到答案，标注为“简历中未找到该信息”
            <回答集合>
            {responsesList}
            </回答集合>

            请严格按照以下JSON格式返回结果：
            {{
                "answers": [
                    {{
                        "entry_id": "字段ID",
                        "question": "问题内容",
                        "answer": "你的最终答案"
                    }},
                    ...
                ]
            }}

            重要提示：确保响应是有效的JSON格式，属性名和字符串值需用双引号包裹，不可使用单引号。
        """)
        
        try:
            # 清理结果文本（去除首尾空白）
            result_text = result.text.strip()
            
            # 若存在LaTeX格式（如\boxed{}），移除该格式
            if '\\boxed{' in result_text:
                start_idx = result_text.find('\\boxed{') + 7  # 跳过\boxed{
                end_idx = result_text.rfind('}')              # 找到最后一个}
                if start_idx > 6 and end_idx > start_idx:
                    result_text = result_text[start_idx:end_idx]
            
            # 尝试解析JSON结果
            try:
                result_json = json.loads(result_text)
            except json.JSONDecodeError:
                # 若解析失败，用原始回答构建标准JSON
                result_json = {
                    "answers": [
                        {
                            "entry_id": r.entry_id,
                            "question": r.field,
                            "answer": r.response
                        } for r in responses
                    ]
                }
            
            # 构建表单提交数据（key为字段ID，value为最终答案）
            submission_data = {}
            for answer in result_json["answers"]:
                entry_id = answer["entry_id"]
                submission_data[entry_id] = answer["answer"]
            
            # 存储两种格式的数据：展示用（带问题）和提交用（仅ID+答案）
            final_data = {
                "display": result_json,       # 供用户审核的展示数据
                "submission": submission_data # 供表单提交的结构化数据
            }
            
            # 将最终数据存储到上下文（无需JSON编码）
            await ctx.set("filled_form", final_data)
            
            # 返回展示数据，让用户审核并提供反馈
            return InputRequiredEvent(
                prompt="""请审核已填写的表单并提供反馈。
                请在下方输入你的反馈：""",
                prefix="你的反馈： ",
                request_type="Feedback",
                result=final_data
            )
            
        except Exception as e:
            print(f"处理表单数据时出错：{str(e)}")
            # 若处理失败，使用原始回答构建fallback数据
            fallback_data = {
                "answers": [
                    {
                        "entry_id": r.entry_id,
                        "question": r.field,
                        "answer": r.response
                    } for r in responses
                ]
            }
            
            # 构建fallback提交数据
            submission_data = {}
            for answer in fallback_data["answers"]:
                entry_id = answer["entry_id"]
                submission_data[entry_id] = answer["answer"]
            
            final_data = {
                "display": fallback_data,
                "submission": submission_data
            }
            
            # 存储fallback数据到上下文
            await ctx.set("filled_form", final_data)
            
            # 返回fallback数据供用户审核
            return InputRequiredEvent(
                prompt="""请审核已填写的表单并提供反馈。
                请在下方输入你的反馈：""",
                prefix="你的反馈： ",
                request_type="Feedback",
                result=final_data
            )
    
    @step
    async def get_feedback(self, ctx: Context, ev: HumanResponseEvent) -> FeedbackEvent | StopEvent:
        # 调用AI分析用户反馈，判断是否需要重新优化回答
        result = self.llm.complete(f"""
            你已收到人类对所提供答案的反馈。请分析该反馈并判断是否需要进行修改。
            
            <反馈内容>
            {ev.response}
            </反馈内容>
            
            响应指导原则：
            1. 若反馈表明“一切正确”或“无需修改”，仅回复“OKAY”
            2. 若反馈建议“需要修改”或“需要优化”，仅回复“FEEDBACK”
            3. 保守判断：若存在任何疑问，均回复“FEEDBACK”
            
            注意：仅允许回复单个单词，要么是“OKAY”，要么是“FEEDBACK”。
        """)
        
        # 提取AI判断结果（去除格式和空白，统一为大写）
        verdict = result.text.strip()
        # 移除可能的LaTeX格式（如\boxed{}）
        verdict = verdict.replace('\\boxed{', '').replace('}', '')
        # 统一格式：去除空白+大写
        verdict = verdict.strip().upper()
        
        print(f"大语言模型（LLM）判断结果：{verdict}")
        
        # 获取当前已填写的表单数据
        filled_form = await ctx.get("filled_form")
        if filled_form:
            try:
                # 处理表单数据格式（若为字符串则解析为JSON）
                if isinstance(filled_form, str):
                    form_data = json.loads(filled_form)
                else:
                    form_data = filled_form
                
                # 若AI判断“无需修改”，返回提交数据并结束流程
                if "OKAY" in verdict:
                    # 生成格式正确的JSON提交数据
                    submission_data = json.dumps(form_data["submission"], ensure_ascii=False, indent=2)
                    return StopEvent(result=submission_data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"处理已填写表单数据时出错：{str(e)}")
                # 若处理失败，返回结构化错误信息
                error_response = {
                    "error": str(e),
                    "message": "表单数据处理失败"
                }
                return StopEvent(result=json.dumps(error_response, ensure_ascii=False, indent=2))
        
        # 若AI判断“需要修改”，返回反馈事件，重新优化回答
        return FeedbackEvent(feedback=ev.response)
            
if __name__ == "__main__":
    async def main():
        # 示例：谷歌表单URL
        url="https://docs.google.com/forms/d/e/1FAIpQLSchbdsD0MoCCqE8quU3pqQ3zO2qfZxPH_SBjgllfzNhqa-FUQ/viewform"
        # 初始化谷歌表单处理器
        form_handler = GoogleFormHandler(url=url)
        # 以DataFrame格式获取表单问题（获取前3个，包含非必填项）
        questions_df = form_handler.get_form_questions_df(only_required=False).head(3)
        # 转换为字典列表格式（便于后续处理）
        form_data = questions_df.to_dict(orient="records")
        
        # 初始化简历处理器（存储目录为"resume_indexes"）
        processor = ResumeProcessor(storage_dir="resume_indexes")
        # 示例：处理本地简历文件（替换为你的简历路径）
        result = processor.process_file("/Users/ajitkumarsingh/AutoFormAgent/asset/resume.pdf")
        
        # 初始化工作流（超时时间1000秒，显示详细日志）
        workflow = RAGWorkflowWithHumanFeedback(timeout=1000, verbose=True)
        # 运行工作流（需传入必要参数）
        handler =  workflow.run(
            resume_index_path="resume_indexes",  # 简历索引目录
            form_data=form_data,                 # 表单数据
            openrouter_key=get_openrouter_api_key(),  # OpenRouter API密钥（需提前定义获取函数）
            llama_cloud_key=get_llama_cloud_api_key(),# Llama Cloud API密钥（需提前定义获取函数）
            selected_model="gryphe/mythomax-l2-13b"   # 选中的LLM模型
        )

        # 流式监听工作流事件
        async for event in handler.stream_events():
            # 若需要用户输入（审核反馈）
            if isinstance(event, InputRequiredEvent):
                print("我们已为你填写完表单，结果如下：\n")
                print("已填写的表单：")
                result_json = event.result

                # 打印展示用数据（带问题和答案）
                print(result_json["display"])
                # 获取用户反馈
                response = input(event.prefix)
                # 发送用户反馈事件
                handler.ctx.send_event(
                    HumanResponseEvent(
                        response=response
                    )
                )
        # 获取工作流最终结果
        response = await handler
        print("最终结果：")
        print(response)
    
    # 运行主函数
    import asyncio
    asyncio.run(main())