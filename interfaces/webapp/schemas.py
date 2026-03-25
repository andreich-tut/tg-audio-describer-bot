"""
Pydantic request/response schemas for the Mini App API.
"""

from enum import Enum

from pydantic import BaseModel, Field


class OAuthStatus(BaseModel):
    connected: bool
    login: str | None = None


class SettingsResponse(BaseModel):
    settings: dict[str, str | None]
    oauth: dict[str, OAuthStatus]


class SettingUpdate(BaseModel):
    value: str = Field(max_length=500)


class SettingKey(str, Enum):
    llm_api_key = "llm_api_key"
    llm_base_url = "llm_base_url"
    llm_model = "llm_model"
    yadisk_path = "yadisk_path"
    obsidian_vault_path = "obsidian_vault_path"
    obsidian_inbox_folder = "obsidian_inbox_folder"


class SectionId(str, Enum):
    llm = "llm"
    yadisk = "yadisk"
    obsidian = "obsidian"


# Keys that are privileged and only accessible to ALLOWED_USER_IDS
PRIVILEGED_KEYS: set[str] = {"obsidian_vault_path"}

# Section → key mapping for bulk reset
SECTION_KEYS: dict[str, list[str]] = {
    "llm": ["llm_api_key", "llm_base_url", "llm_model"],
    "yadisk": ["yadisk_path"],
    "obsidian": ["obsidian_vault_path", "obsidian_inbox_folder"],
}

# Keys whose values should be masked in GET responses
SECRET_KEYS: set[str] = {"llm_api_key"}
