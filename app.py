"""
AI自动填求职申请表工具

一款基于Streamlit的网页应用，可通过AI自动填写求职申请表。
该应用能处理简历、提取关键信息，并结合人工反馈确保填写准确性，最终完成谷歌表单（Google Forms）的填写。

作者：Ajit Kumar Singh
日期：2025
"""

import streamlit as st
import tempfile
from pathlib import Path
import logging
import asyncio
import json
import nest_asyncio
import time

from resume_processor import ResumeProcessor  # 简历处理器（外部模块）
from google_form_handler import GoogleFormHandler  # 谷歌表单处理器（外部模块）
from rag_workflow_with_human_feedback import RAGWorkflowWithHumanFeedback  # 带人工反馈的RAG工作流（外部模块）
from llama_index.core.workflow import InputRequiredEvent, HumanResponseEvent, StopEvent  # 工作流事件类

# 配置日志系统，便于调试和监控
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 启用嵌套事件循环，支持在Streamlit中运行异步操作
nest_asyncio.apply()

def initialize_session_state():
    """
    初始化应用中所有用到的会话状态变量。
    确保所有必需变量都已存在且初始化正确，避免后续调用时出现变量未定义错误。
    """
    # 核心应用状态（工具实例）
    if 'resume_processor' not in st.session_state:  # 简历处理器实例
        st.session_state.resume_processor = None
    if 'form_handler' not in st.session_state:  # 表单处理器实例
        st.session_state.form_handler = None
    if 'workflow' not in st.session_state:  # RAG工作流实例
        st.session_state.workflow = None
    if 'workflow_handler' not in st.session_state:  # 工作流处理器实例
        st.session_state.workflow_handler = None
    
    # 流程状态跟踪（记录当前进度和数据）
    if 'resume_processed' not in st.session_state:  # 简历是否已处理完成
        st.session_state.resume_processed = False
    if 'current_step' not in st.session_state:  # 当前处于流程的第几步
        st.session_state.current_step = 0
    if 'form_data' not in st.session_state:  # 表单的原始数据（问题列表等）
        st.session_state.form_data = None
    if 'filled_form' not in st.session_state:  # AI已填写好的表单数据
        st.session_state.filled_form = None
    if 'resume_index_path' not in st.session_state:  # 简历解析后生成的索引文件路径
        st.session_state.resume_index_path = None
    if 'event_loop' not in st.session_state:  # 异步操作的事件循环
        st.session_state.event_loop = None
    
    # API和模型配置（用户提供的关键信息）
    if 'openrouter_key' not in st.session_state:  # OpenRouter的API密钥（用于调用AI模型）
        st.session_state.openrouter_key = None
    if 'llama_cloud_key' not in st.session_state:  # Llama Cloud的API密钥（用于解析简历）
        st.session_state.llama_cloud_key = None
    if 'final_form_filled' not in st.session_state:  # 最终确认的填写结果
        st.session_state.final_form_filled = None
    if 'selected_model' not in st.session_state:  # 用户选择的AI模型标识
        st.session_state.selected_model = None
    if 'form_url' not in st.session_state:  # 目标谷歌表单的URL
        st.session_state.form_url = None
    
    # 反馈系统状态（记录人工反馈相关数据）
    if 'feedback_submitted' not in st.session_state:  # 反馈是否已提交
        st.session_state.feedback_submitted = False
    if 'current_feedback' not in st.session_state:  # 当前用户输入的反馈内容
        st.session_state.current_feedback = None
    if 'feedback_count' not in st.session_state:  # 反馈提交的次数
        st.session_state.feedback_count = 0
    if 'last_event_type' not in st.session_state:  # 上一次处理的工作流事件类型
        st.session_state.last_event_type = None
    if 'waiting_for_feedback' not in st.session_state:  # 是否处于等待用户反馈的状态
        st.session_state.waiting_for_feedback = False
    if 'feedback_states' not in st.session_state:  # 各步骤的反馈状态记录
        st.session_state.feedback_states = {}

# 定义可用的AI模型，键为模型名称（显示给用户），值为对应的OpenRouter标识（后台调用用）
OPENROUTER_MODELS = {
    "Mistral 7B Instruct": "mistralai/mistral-7b-instruct:free",
    "DeepSeek R1": "deepseek/deepseek-r1-zero:free",
    "MythoMax L2 13B": "gryphe/mythomax-l2-13b",
    "Llama 2 70B": "meta-llama/llama-2-70b-chat:free",
    "Claude 2.1": "anthropic/claude-2.1",
    "GPT-4": "openai/gpt-4",
    "GPT-3.5 Turbo": "openai/gpt-3.5-turbo"
}

def process_resume(file_input: str) -> bool:
    """
    处理上传的简历，生成可搜索的索引（便于后续AI提取信息）。
    
    参数：
        file_input (str): 简历文件的本地路径或谷歌云盘链接
        
    返回：
        bool: 处理成功返回True，失败返回False
    """
    try:
        # 显示"处理中"的加载动画
        with st.spinner("正在处理您的简历..."):
            # 调用简历处理器的处理方法
            result = st.session_state.resume_processor.process_file(file_input)
            print(result)  # 打印结果（调试用）
            
            # 处理成功：记录索引路径并提示用户
            if result["success"]:
                st.session_state.resume_index_path = result["index_location"]
                st.success(f"简历处理成功！已生成 {result['num_nodes']} 个可搜索的内容片段。")
                return True
            # 处理失败：根据错误类型提示不同信息
            else:
                error_msg = result["error"]
                # 特殊处理"服务暂时不可用"错误
                if "503 Service Temporarily Unavailable" in error_msg:
                    st.error("""
                    简历处理服务暂时不可用，请几分钟后再尝试。
                    
                    若问题持续，可尝试以下操作：
                    1. 检查网络连接是否正常
                    2. 等待几分钟后重新尝试
                    3. 使用其他版本的简历文件
                    """)
                # 其他错误直接显示详情
                else:
                    st.error(f"简历处理失败：{error_msg}")
                return False
    # 捕获所有未预料到的异常
    except Exception as e:
        error_msg = str(e)
        # 同样特殊处理"服务暂时不可用"
        if "503 Service Temporarily Unavailable" in error_msg:
            st.error("""
            简历处理服务暂时不可用，请几分钟后再尝试。
            
            若问题持续，可尝试以下操作：
            1. 检查网络连接是否正常
            2. 等待几分钟后重新尝试
            3. 使用其他版本的简历文件
            """)
        else:
            st.error(f"简历处理时发生错误：{error_msg}")
        return False

def display_progress_bar():
    """显示进度条，直观展示当前在申请表填写流程中的步骤。"""
    # 流程的所有步骤名称
    steps = ["上传简历", "处理表单", "审核与反馈", "提交表单"]
    # 计算进度（当前步骤/总步骤数-1，因为步骤从0开始）
    progress = st.session_state.current_step / (len(steps) - 1)
    st.progress(progress)
    # 显示当前步骤的具体信息（如"Step 1 of 4: 上传简历"）
    st.caption(f"第 {st.session_state.current_step + 1} 步 / 共 {len(steps)} 步：{steps[st.session_state.current_step]}")

def add_back_button():
    """添加返回按钮，允许用户导航到上一步（仅当当前不是第一步时显示）。"""
    if st.session_state.current_step > 0:
        # 按钮点击后，步骤减1并重新加载页面
        if st.button("← 返回", key=f"back_{st.session_state.current_step}"):
            st.session_state.current_step -= 1
            st.rerun()

async def run_workflow(form_data):
    """
    运行带人工反馈的RAG工作流（核心逻辑）。
    
    该函数管理整个工作流程，包括：
    - 初始化工作流实例
    - 处理用户的反馈提交
    - 监听并处理工作流事件（如需要输入、流程结束）
    - 管理最终的表单填写结果
    
    参数：
        form_data: 需要处理的表单原始数据（包含问题列表等）
        
    返回：
        dict: 最终处理完成的表单数据；若处理失败，返回None
    """
    try:
        # 先检查简历索引是否存在（没有索引则无法提取信息）
        if not st.session_state.resume_index_path:
            st.error("未找到简历索引文件，请重新处理简历。")
            return None

        # 记录日志：工作流启动信息
        logger.info("工作流启动，使用简历索引路径：%s", st.session_state.resume_index_path)
        logger.info("待处理的表单数据：%s", form_data)

        # 初始化工作流（仅当工作流实例不存在时）
        if st.session_state.workflow is None:
            st.session_state.workflow = RAGWorkflowWithHumanFeedback(timeout=1000, verbose=True)
            logger.info("已创建新的工作流实例")
            # 重置相关状态（避免残留旧数据）
            st.session_state.workflow_handler = None
            st.session_state.feedback_count = 0
            st.session_state.current_feedback = None
            st.session_state.last_event_type = None
            st.session_state.waiting_for_feedback = False
            st.session_state.feedback_submitted = False

        # 创建或获取工作流处理器（负责实际运行工作流）
        if st.session_state.workflow_handler is None:
            logger.info("创建新的工作流处理器")
            st.session_state.workflow_handler = st.session_state.workflow.run(
                resume_index_path=st.session_state.resume_index_path,  # 简历索引路径
                form_data=form_data,  # 表单原始数据
                openrouter_key=st.session_state.openrouter_key,  # OpenRouter API密钥
                llama_cloud_key=st.session_state.llama_cloud_key,  # Llama Cloud API密钥
                selected_model=st.session_state.selected_model  # 用户选择的AI模型
            )
            logger.info("工作流处理器创建完成")

        # 处理"等待用户反馈"的状态
        if st.session_state.get('waiting_for_feedback', False):
            logger.info("当前处于等待用户反馈的状态")
            
            # 为反馈相关的UI元素生成唯一键（避免Streamlit缓存导致的显示问题）
            feedback_key = f"feedback_{st.session_state.feedback_count}"
            submit_key = f"submit_{feedback_key}"
            
            # 显示"表单填写结果审核"标题
            st.subheader("📝 表单填写结果审核")
            
            # 以可展开的形式显示每个问题的填写结果
            if st.session_state.filled_form and "display" in st.session_state.filled_form and "answers" in st.session_state.filled_form["display"]:
                for answer in st.session_state.filled_form["display"]["answers"]:
                    with st.expander(f"问题：{answer['question']}", expanded=True):
                        st.write("**字段ID：** ", answer["entry_id"])
                        st.write("**填写答案：** ", answer["answer"])
                        st.divider()  # 分割线，增强可读性
            
            # 让用户输入反馈（文本框）
            feedback = st.text_area(
                "审核填写结果并提供反馈：",
                key=feedback_key,
                help="若答案正确，直接输入'OK'即可；若需修改，请提供具体的优化建议（如'联系方式填错了，应为138xxxx1234'）。"
            )
            
            # 实时显示用户当前输入的反馈内容
            if feedback:
                st.info(f"当前反馈内容：{feedback}")
            
            # 反馈提交按钮的状态容器（用于显示加载/成功/失败提示）
            status_container = st.empty()
            submit_clicked = st.button(
                "提交反馈",
                key=submit_key,
                type="primary",  # primary类型按钮（蓝色，突出显示）
                use_container_width=True  # 按钮宽度适应容器
            )
            
            # 处理反馈提交操作
            if submit_clicked:
                # 检查反馈是否为空
                if not feedback:
                    status_container.warning("⚠️ 请先输入反馈内容再提交。")
                else:
                    try:
                        status_container.info("🔄 正在处理反馈...")
                        logger.info(f"提交第 {st.session_state.feedback_count} 次反馈：{feedback}")
                        
                        # 更新会话状态：记录反馈内容、标记反馈已提交、退出等待状态
                        st.session_state.current_feedback = feedback
                        st.session_state.feedback_submitted = True
                        st.session_state.waiting_for_feedback = False
                        
                        # 等待0.5秒（确保UI有时间更新），然后重新加载页面
                        time.sleep(0.5)
                        st.rerun()
                        
                    except Exception as e:
                        error_msg = f"准备反馈时出错：{str(e)}"
                        logger.error(error_msg)
                        status_container.error(f"❌ {error_msg}")
            
            # 若反馈未提交，返回None（等待用户操作）
            if not st.session_state.get('feedback_submitted', False):
                return None
        
        # 处理"反馈已提交"的状态（将反馈发送给工作流）
        if st.session_state.get('feedback_submitted', False):
            try:
                logger.info(f"将反馈发送给工作流：{st.session_state.current_feedback}")
                
                # 向工作流发送"人工反馈事件"
                st.session_state.workflow_handler.ctx.send_event(
                    HumanResponseEvent(
                        response=st.session_state.current_feedback
                    )
                )
                
                # 重置反馈相关状态（准备接收下一次反馈）
                st.session_state.feedback_submitted = False
                st.session_state.feedback_count += 1
                
                logger.info("反馈已发送，工作流继续运行")
                
            except Exception as e:
                logger.error(f"发送反馈时出错：{str(e)}", exc_info=True)  # 记录详细错误栈
                st.error(f"发送反馈时出错：{str(e)}")
                # 重置状态，让用户重新提交反馈
                st.session_state.feedback_submitted = False
                st.session_state.waiting_for_feedback = True
                return None
        
        # 处理工作流事件（循环监听事件，直到流程结束）
        final_result = None
        try:
            # 异步遍历工作流产生的事件
            async for event in st.session_state.workflow_handler.stream_events():
                logger.info("收到工作流事件：%s", type(event).__name__)
                st.session_state.last_event_type = type(event).__name__
                
                # 处理"需要输入"事件（工作流需要用户反馈才能继续）
                if isinstance(event, InputRequiredEvent):
                    logger.info("处理InputRequiredEvent事件（需要用户反馈）")
                    result_data = event.result
                    
                    # 更新会话状态：记录当前填写结果、进入等待反馈状态
                    st.session_state.filled_form = result_data
                    st.session_state.waiting_for_feedback = True
                    
                    # 重新加载页面（显示反馈界面）
                    st.rerun()
                    return None
                    
                # 处理"流程结束"事件（工作流完成所有任务）
                elif isinstance(event, StopEvent):
                    logger.info("收到StopEvent事件（工作流已完成）")
                    # 检查是否有最终结果
                    if hasattr(event, 'result') and event.result is not None:
                        try:
                            # 解析最终结果（支持JSON字符串或字典格式）
                            if isinstance(event.result, str):
                                try:
                                    final_result = json.loads(event.result)  # 尝试将字符串解析为JSON
                                    logger.info("成功将结果解析为JSON格式")
                                except json.JSONDecodeError:
                                    # 解析失败，按原始字符串处理
                                    logger.warning("结果不是有效的JSON格式，按原始字符串存储")
                                    final_result = {"error": "结果解析为JSON失败", "raw": event.result}
                            elif isinstance(event.result, dict):
                                final_result = event.result  # 已为字典，直接使用
                                logger.info("结果已是字典格式，无需解析")
                            else:
                                # 不支持的结果类型
                                logger.error(f"意外的结果类型：{type(event.result)}")
                                final_result = {"error": f"意外的结果类型：{type(event.result)}"}
                                
                            # 记录结果的结构信息（调试用）
                            logger.info(f"最终结果类型：{type(final_result)}")
                            if isinstance(final_result, dict):
                                logger.info(f"最终结果包含的键：{final_result.keys()}")
                            
                            # 更新会话状态：记录最终填写结果、推进到下一步
                            st.session_state.filled_form = final_result
                            st.session_state.final_form_filled = final_result
                            st.session_state.current_step += 1
                            
                            # 清理工作流状态（释放资源，避免影响下次使用）
                            st.session_state.workflow = None
                            st.session_state.workflow_handler = None
                            st.session_state.waiting_for_feedback = False
                            st.session_state.feedback_submitted = False
                            
                            # 重新加载页面（进入下一步：提交表单）
                            st.rerun()
                            return final_result
                            
                        except Exception as e:
                            logger.error(f"处理最终结果时出错：{str(e)}", exc_info=True)
                            st.error(f"处理最终表单数据时出错：{str(e)}")
                            return None
                    else:
                        logger.warning("收到StopEvent事件，但无最终结果")
                        st.warning("未收到最终结果，请重新尝试。")
                        return None
            
            # 事件流结束但未收到StopEvent（异常情况）
            logger.info("事件流已结束，但未收到StopEvent事件")
            
            # 尝试直接从工作流处理器获取结果
            try:
                direct_result = await st.session_state.workflow_handler
                logger.info(f"从工作流处理器直接获取结果：{direct_result}")
                
                if direct_result:
                    # 解析直接获取的结果（逻辑同上）
                    if isinstance(direct_result, str):
                        try:
                            final_result = json.loads(direct_result)
                            logger.info("成功解析直接获取的结果为JSON")
                        except json.JSONDecodeError:
                            logger.warning("直接获取的结果不是有效JSON，按原始字符串处理")
                            final_result = {"error": "直接结果解析为JSON失败", "raw": direct_result}
                    elif isinstance(direct_result, dict):
                        final_result = direct_result
                        logger.info("直接获取的结果已是字典格式")
                    else:
                        logger.warning(f"意外的直接结果类型：{type(direct_result)}")
                        final_result = {"error": f"意外的直接结果类型：{type(direct_result)}"}
                    
                    # 更新会话状态并推进步骤
                    st.session_state.filled_form = final_result
                    st.session_state.final_form_filled = final_result
                    st.session_state.current_step += 1
                    
                    # 清理工作流状态
                    st.session_state.workflow = None
                    st.session_state.workflow_handler = None
                    st.session_state.waiting_for_feedback = False
                    st.session_state.feedback_submitted = False
                    
                    # 重新加载页面
                    st.rerun()
                    return final_result
            except Exception as e:
                logger.error(f"直接获取结果时出错：{str(e)}", exc_info=True)
            
            #  fallback：使用已有的填写结果（若存在）
            if st.session_state.filled_form:
                logger.info("使用已有的表单填写结果")
                return st.session_state.filled_form
            
            # 无任何结果可用
            logger.warning("无可用结果")
            st.warning("无可用结果，请重新尝试。")
            return None
                
        # 捕获工作流被取消的异常
        except asyncio.CancelledError:
            logger.warning("工作流已被取消")
            st.warning("工作流已被取消，请重新尝试。")
            return None
            
    # 捕获所有未预料到的异常
    except Exception as e:
        logger.error("工作流运行时出错：%s", str(e), exc_info=True)
        st.error(f"工作流运行时出错：{str(e)}")
        return None

def main():
    """
    应用程序主入口。
    负责设置Streamlit界面的基础配置、管理会话状态，并控制整个申请表填写流程的步骤切换。
    """
    # 配置页面基础设置（标题、图标、布局）
    st.set_page_config(
        page_title="简历自动填表单工具",
        page_icon="📝",
        layout="wide"  # 宽屏布局，适配更多内容
    )
    
    # 初始化会话状态（确保所有变量已定义）
    initialize_session_state()
    
    # 侧边栏：用于API密钥配置、模型选择和帮助信息
    with st.sidebar:
        st.markdown("### 🔑 API密钥配置")
        
        # 输入OpenRouter API密钥（密码类型，隐藏输入内容）
        openrouter_key = st.text_input(
            "OpenRouter API密钥",
            type="password",
            help="AI处理必需，从 https://openrouter.ai/keys 获取"
        )
        if openrouter_key:
            st.session_state.openrouter_key = openrouter_key  # 保存到会话状态
            
        # 输入Llama Cloud API密钥（密码类型）
        llama_cloud_key = st.text_input(
            "Llama Cloud API密钥",
            type="password",
            help="简历解析必需，从 https://cloud.llamaindex.ai/ 获取"
        )
        if llama_cloud_key:
            st.session_state.llama_cloud_key = llama_cloud_key  # 保存到会话状态
            # 用新密钥初始化简历处理器
            st.session_state.resume_processor = ResumeProcessor(
                storage_dir="resume_indexes",  # 简历索引的存储目录
                llama_cloud_api_key=llama_cloud_key  # 传入Llama Cloud密钥
            )
            
        # 侧边栏：AI模型选择
        st.markdown("### 🤖 模型选择")
        selected_model_name = st.selectbox(
            "选择AI模型",
            options=list(OPENROUTER_MODELS.keys()),  # 显示所有可用模型名称
            help="""选择用于处理简历的AI模型。
            标注':free'的为免费模型，付费模型需在OpenRouter平台充值后使用，可能提供更优效果。"""
        )
        if selected_model_name:
            # 保存选中模型的OpenRouter标识（后台调用用）
            st.session_state.selected_model = OPENROUTER_MODELS[selected_model_name]
            # 显示模型的详细信息（是否免费）
            st.info(f"""已选模型：{selected_model_name}
            模型ID：{st.session_state.selected_model}
            {'🆓 该模型为免费模型' if ':free' in st.session_state.selected_model else '💰 该模型为付费模型'}""")
            
        # 侧边栏：API密钥获取指南
        st.markdown("### 📋 如何获取API密钥")
        st.markdown("""
        **获取OpenRouter API密钥：**
        1. 访问 [OpenRouter官网](https://openrouter.ai/)
        2. 注册或登录账号
        3. 进入"API Keys"页面
        4. 创建新密钥并复制
        
        **获取Llama Cloud API密钥：**
        1. 访问 [Llama Cloud官网](https://cloud.llamaindex.ai/)
        2. 创建账号并登录
        3. 进入"API Keys"页面
        4. 生成新密钥并复制
        """)
        
        # 侧边栏：应用限制和使用建议
        st.markdown("### ⚠️ 重要限制")
        st.markdown("""
        - 最多支持处理10个问题的表单
        - 仅支持PDF格式简历（最大10MB）
        - 表单复杂度越高，处理时间越长
        - 需保持稳定的网络连接
        - 所有功能都需要API密钥才能使用
        
        **使用建议：**
        - 使用内容清晰的单页简历（AI提取信息更准确）
        - 提交前务必核对所有表单字段
        - 仔细审核AI生成的答案，有误及时修改
        - 提供详细反馈，帮助AI优化后续结果
        """)
        
        # 侧边栏：应用工作原理
        st.markdown("### 工具工作流程：")
        st.markdown("""
        1. **上传简历**：上传PDF简历或提供谷歌云盘链接
        2. **处理表单**：输入谷歌表单URL，解析表单字段
        3. **审核与反馈**：查看AI填写结果，提供修改反馈
        4. **提交表单**：确认无误后，提交最终申请表
        
        ### 核心功能：
        - 支持PDF和谷歌云盘简历
        - AI自动提取简历信息
        - 人工反馈优化结果
        - 实时进度跟踪
        - 错误提示与处理
        """)
    
    # 主界面：标题和功能简介
    st.title("📝 求职申请表自动填写工具")
    st.write("""
    上传您的简历并输入谷歌表单链接，工具将自动从简历中提取信息，完成表单填写！
    """)
    
    # 检查关键配置是否完成（API密钥和模型选择），未完成则提示用户
    if not st.session_state.openrouter_key:
        st.warning("⚠️ 请在侧边栏输入OpenRouter API密钥后继续。")
        return  # 终止执行，等待用户配置
    if not st.session_state.llama_cloud_key:
        st.warning("⚠️ 请在侧边栏输入Llama Cloud API密钥后继续。")
        return
    if not st.session_state.selected_model:
        st.warning("⚠️ 请在侧边栏选择AI模型后继续。")
        return
    
    # 显示进度条（当前步骤）
    display_progress_bar()
    
    # 添加返回按钮（在每个步骤顶部显示）
    add_back_button()
    
    # 步骤1：上传简历（流程的第一步）
    if st.session_state.current_step == 0:
        st.header("步骤1：上传简历")
        # 让用户选择简历来源（本地PDF或谷歌云盘链接）
        resume_source = st.radio(
            "选择简历来源：",
            ["上传本地PDF", "谷歌云盘链接"]
        )
        
        # 分支1：用户选择"上传本地PDF"
        if resume_source == "上传本地PDF":
            uploaded_file = st.file_uploader("上传您的简历（仅支持PDF格式）", type=['pdf'])
            if uploaded_file:
                # 检查文件大小（限制10MB）
                if uploaded_file.size > 10 * 1024 * 1024:  # 10MB = 10*1024*1024字节
                    st.error("文件大小超过10MB限制，请上传更小的PDF文件。")
                    return
                    
                # 临时保存上传的文件（Streamlit上传的文件需先保存到本地才能处理）
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    resume_path = tmp_file.name  # 获取临时文件路径
                
                # 处理简历，成功则推进到下一步
                if process_resume(resume_path):
                    st.session_state.resume_processed = True
                    st.session_state.current_step += 1
                    st.rerun()  # 重新加载页面，进入步骤2
                
                # 删除临时文件（避免占用空间）
                Path(resume_path).unlink()
                
        # 分支2：用户选择"谷歌云盘链接"
        else:
            drive_link = st.text_input("输入简历的谷歌云盘链接：")
            # 点击"处理简历"按钮后执行
            if drive_link and st.button("处理简历"):
                # 处理简历，成功则推进到下一步
                if process_resume(drive_link):
                    st.session_state.resume_processed = True
                    st.session_state.current_step += 1
                    st.rerun()
    
    # 步骤2：处理表单（解析谷歌表单的问题字段）
    elif st.session_state.current_step == 1:
        st.header("步骤2：处理表单")
        # 让用户输入谷歌表单URL
        form_url = st.text_input("输入目标谷歌表单的URL：")
        
        if form_url:
            try:
                # 显示"解析中"的加载动画
                with st.spinner("正在分析表单字段..."):
                    # 初始化谷歌表单处理器
                    form_handler = GoogleFormHandler(url=form_url)
                    # 获取表单的问题列表（转为DataFrame，包含问题、字段ID等）
                    questions_df = form_handler.get_form_questions_df(only_required=False)
                    
                    # 检查问题数量（限制最多10个）
                    if len(questions_df) >= 20:
                        st.error("⚠️ 该表单包含超过20个问题，目前仅支持最多10个问题的表单（确保处理性能）。")
                        return
                        
                    # 保存表单数据到会话状态
                    st.session_state.form_data = questions_df.to_dict(orient="records")  # 转为字典列表
                    st.session_state.form_url = form_url
                    
                    # 显示表单预览（让用户确认字段是否正确）
                    st.subheader("表单字段预览")
                    st.dataframe(questions_df)  # 用表格显示问题列表
                    
                    # 估算处理时间（每个问题约15秒）
                    est_time = len(questions_df) * 15
                    st.info(f"ℹ️ 预计处理时间：{est_time} 秒（根据问题数量估算）")
                    
                    # 点击"继续审核"按钮，推进到步骤3
                    if st.button("继续审核"):
                        st.session_state.current_step += 1
                        st.rerun()
                        
            # 捕获解析表单时的异常
            except Exception as e:
                st.error(f"解析表单时出错：{str(e)}")
    
    # 步骤3：审核与反馈（查看AI填写结果并提供反馈）
    elif st.session_state.current_step == 2:
        st.header("步骤3：审核与反馈")
        
        # 检查表单数据是否存在（避免异常）
        if st.session_state.form_data:
            logger.info("当前表单数据：%s", st.session_state.form_data)
            logger.info("当前已填写的表单状态：%s", st.session_state.filled_form)
            
            # 初始化异步事件循环（若未初始化）
            if st.session_state.event_loop is None:
                st.session_state.event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(st.session_state.event_loop)
            
            # 运行工作流（异步操作，需用事件循环执行）
            result = st.session_state.event_loop.run_until_complete(run_workflow(st.session_state.form_data))
            logger.info("工作流返回结果：%s", result)
            
            # 若工作流返回有效结果，推进到步骤4（提交表单）
            if result and isinstance(result, dict) and "submission" in result:
                st.session_state.filled_form = result
                st.session_state.final_form_filled = result
                
                if st.session_state.current_step < 3:
                    st.session_state.current_step = 3
                    st.rerun()
    
    # 步骤4：提交表单（最终步骤，将填写好的内容提交到谷歌表单）
    elif st.session_state.current_step == 3:
        st.header("步骤4：提交申请表")
        
        logger.info("进入最终提交步骤，当前已填写的表单：%s", st.session_state.filled_form)
        
        # 检查是否有已填写的表单数据（无数据则提示返回上一步）
        if not st.session_state.filled_form:
            st.error("无可用的表单填写数据，请返回上一步完成审核。")
            if st.button("返回上一步"):
                st.session_state.current_step = 2
                st.rerun()
        else:
            try:
                form_data = st.session_state.filled_form
                logger.info("待提交的表单数据：%s", form_data)
                
                # 点击"提交申请表"按钮执行提交操作
                if st.button("提交申请表", type="primary"):
                    try:
                        logger.info("尝试提交表单到URL：%s", st.session_state.form_url)
                        # 初始化表单处理器
                        form_handler = GoogleFormHandler(url=st.session_state.form_url)
                        
                        # 验证表单数据格式（必须是字典）
                        if not isinstance(form_data, dict):
                            st.error("表单数据格式无效，请重新尝试。")
                            logger.error("表单数据不是字典类型")
                            return
                            
                        # 确保所有必填字段都已填写且格式正确（适配谷歌表单的字段ID格式）
                        required_fields = form_handler.get_form_questions_df(only_required=True)  # 获取必填字段
                        missing_fields = []  # 记录未填写的必填字段
                        formatted_data = {}  # 格式化后的字段数据（适配谷歌表单）
                        
                        # 遍历所有必填字段，检查并格式化
                        for _, row in required_fields.iterrows():
                            field_id = row['Entry_ID']  # 字段ID
                            # 检查该字段是否有填写内容
                            if field_id not in form_data or not form_data[field_id]:
                                missing_fields.append(row['Question'])  # 记录未填写的问题
                            else:
                                # 谷歌表单的字段ID需以"entry."开头，若没有则补全
                                if field_id.startswith('entry.'):
                                    formatted_data[field_id] = form_data[field_id]
                                else:
                                    formatted_data[f'entry.{field_id}'] = form_data[field_id]
                                
                        # 若有未填写的必填字段，提示用户
                        if missing_fields:
                            st.error(f"缺少必填字段：{', '.join(missing_fields)}")
                            logger.error(f"缺少必填字段：{missing_fields}")
                            return
                        
                        # 提交格式化后的表单数据
                        success = form_handler.submit_form(formatted_data)
                        
                        # 处理提交结果
                        if success:
                            st.success("🎉 申请表提交成功！")
                            st.balloons()  # 显示气球动画（庆祝成功）
                            logger.info("表单提交成功")
                        else:
                            st.error("申请表提交失败，请重新尝试。")
                            logger.error("表单提交失败，无具体异常信息")
                    # 捕获提交时的异常
                    except Exception as e:
                        st.error(f"提交申请表时出错：{str(e)}")
                        logger.error("表单提交出错：%s", str(e), exc_info=True)
            # 捕获准备提交数据时的异常
            except Exception as e:
                st.error(f"准备提交数据时出错：{str(e)}")
                st.text("原始表单数据：")
                st.json(st.session_state.filled_form)  # 显示原始数据（便于用户排查问题）
                logger.error("准备最终提交时出错：%s", str(e))

# 当脚本直接运行时，执行main函数（程序入口）
if __name__ == "__main__":
    main()