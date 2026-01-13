import json
import os
from typing import Dict, Any
from pypdf import PdfReader
from docx import Document
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

class ResumeProcessor:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_API_BASE")
        self.llm = ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            model=model,
            temperature=0
        )
        self.output_parser = JsonOutputParser()
        
    def extract_text(self, file_path: str) -> str:
        """从 PDF、Word 或 文本文件中提取文本"""
        ext = os.path.splitext(file_path)[1].lower()
        text = ""
        if ext == ".pdf":
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif ext in [".docx", ".doc"]:
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
        return text

    def parse_resume(self, text: str) -> Dict[str, Any]:
        """使用 LLM 将简历文本解析为结构化 JSON"""
        prompt = ChatPromptTemplate.from_template(
            "你是一个专业的简历解析助手。请从以下简历文本中提取信息，并以 JSON 格式返回。\n"
            "要求的字段包括：姓名 (name), 邮箱 (email), 电话 (phone), 教育背景 (education), 工作经历 (experience), 技能 (skills)。\n"
            "如果某项信息缺失，请填入空字符串。\n"
            "简历文本：\n{text}\n"
            "请只返回 JSON 对象，不要有任何其他解释。"
        )
        
        chain = prompt | self.llm | self.output_parser
        result = chain.invoke({"text": text})
        return result

    def process(self, file_path: str) -> Dict[str, Any]:
        """全流程处理：提取 + 解析"""
        text = self.extract_text(file_path)
        return self.parse_resume(text)