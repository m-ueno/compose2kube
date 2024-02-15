import unittest
from typing import Any, List, Optional, cast
from unittest.mock import patch

from langchain_core.language_models.base import LanguageModelInput
from langchain_core.messages.base import BaseMessage
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.runnables import RunnableConfig, ensure_config
from langchain_openai import ChatOpenAI


class ChatOpenAIMultiGenerations(ChatOpenAI):
    def invoke(
        self,
        input: LanguageModelInput,
        config: Optional[RunnableConfig] = None,
        *,
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[BaseMessage]:
        config = ensure_config(config)
        gens = self.generate_prompt(
            [self._convert_input(input)],
            stop=stop,
            callbacks=config.get("callbacks"),
            tags=config.get("tags"),
            metadata=config.get("metadata"),
            run_name=config.get("run_name"),
            **kwargs,
        ).generations[0]
        return [cast(ChatGeneration, g).message for g in gens]
