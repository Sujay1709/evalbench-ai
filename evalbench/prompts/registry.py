import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class PromptDefinition(BaseModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = ""
    template: str = Field(min_length=1)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def render(self, inputs: dict) -> str:
        try:
            return self.template.format(**inputs)
        except KeyError as exc:
            raise ValueError(f"Prompt input is missing required field {exc}") from exc


def load_prompt(path: str | Path) -> PromptDefinition:
    prompt_path = Path(path)
    if not prompt_path.is_file():
        raise ValueError(f"Prompt not found: {prompt_path}")
    return PromptDefinition.model_validate(yaml.safe_load(prompt_path.read_text()))
