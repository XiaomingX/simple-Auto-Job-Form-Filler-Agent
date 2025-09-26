from llama_parse import LlamaParse
from pathlib import Path
import os
import logging
from typing import Optional, Dict, Any
import tempfile
import requests

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    ServiceContext
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResumeProcessor:
    def __init__(self, storage_dir: str = "resume_index", llama_cloud_api_key: str = None):
        """
        初始化简历处理器
        
        参数:
            storage_dir: 处理后的索引将存储的目录
            llama_cloud_api_key: Llama Cloud服务的API密钥
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.llama_cloud_api_key = llama_cloud_api_key
        
        # 初始化嵌入模型
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )
        
    def process_file(self, file_input: str) -> Dict[str, Any]:
        """
        处理简历文件并创建可搜索的索引
        
        参数:
            file_input: 本地文件路径或谷歌云盘URL
            
        返回:
            包含处理状态和可能的错误信息的字典
        """
        # 初始化file_path为None，避免未绑定变量错误
        file_path = None
        
        try:
            # 检查API密钥
            if not self.llama_cloud_api_key:
                return {
                    "success": False,
                    "error": "需要Llama Cloud API密钥"
                }

            # 处理文件输入
            file_path = self._get_file_path(file_input)
            if not file_path:
                return {
                    "success": False,
                    "error": "获取文件失败"
                }

            # 解析文档
            try:
                documents = LlamaParse(
                    api_key=self.llama_cloud_api_key,
                    result_type='markdown',
                    system_prompt="这是一份简历，请将相关信息整理在一起，并格式化为带标题的项目符号列表"
                ).load_data(file_path)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"解析文档失败: {str(e)}"
                }

            # 创建索引
            try:
                index = VectorStoreIndex.from_documents(
                    documents,
                    embed_model=self.embed_model
                )
                index.storage_context.persist(persist_dir=self.storage_dir)
                
                return {
                    "success": True,
                    "index_location": str(self.storage_dir),
                    "num_nodes": len(index.ref_doc_info)
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"创建/保存索引失败: {str(e)}"
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"意外错误: {str(e)}"
            }
        finally:
            # 如果是从谷歌云盘下载的文件，清理临时文件
            if file_path and isinstance(file_path, str) and file_path.startswith("https://drive.google.com"):
                try:
                    Path(file_path).unlink()
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {str(e)}")

    def _get_file_path(self, file_input: str) -> Optional[str]:
        """从输入获取本地文件路径（如果是URL则下载）"""
        # 如果是本地文件
        if os.path.isfile(file_input):
            return file_input
            
        # 如果是谷歌云盘URL
        if 'drive.google.com' in file_input:
            return self._download_drive_file(file_input)
            
        return None

    def _download_drive_file(self, url: str) -> Optional[str]:
        """从谷歌云盘下载文件"""
        try:
            # 提取文件ID
            file_id = None
            if '/file/d/' in url:
                file_id = url.split('/file/d/')[1].split('/')[0]
            elif 'id=' in url:
                file_id = url.split('id=')[1].split('&')[0]
                
            if not file_id:
                logger.error("无法从谷歌云盘URL中提取文件ID")
                return None

            # 下载文件
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            # 保存到临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                return temp_file.name

        except Exception as e:
            logger.error(f"下载文件失败: {str(e)}")
            return None

# 示例用法
if __name__ == "__main__":
    pass
