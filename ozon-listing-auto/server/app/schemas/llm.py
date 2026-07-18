from pydantic import BaseModel

class LlmIn(BaseModel):
    llm_provider: str = "mock"      # mock | openai
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

class LlmOut(BaseModel):
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str | None = None   # 脱敏
    llm_model: str = ""
