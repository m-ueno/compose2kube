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


class TestChatOpenAI(unittest.TestCase):
    @patch("openai.resources.chat.completions.Completions.create", autospec=True)
    def test_n(self, mock_create):
        from openai.types.chat.chat_completion import ChatCompletion, Choice
        from openai.types.chat.chat_completion_message import ChatCompletionMessage

        msgs = [
            "こんにちは！いい天気ですね。何かお手伝いできることはありますか？",
            "こんにちは！いつもお世話になっております。どのようなことでお力になれるでしょうか？",
            "こんにちは！どのようなご用件でしょうか？",
        ]
        choices = [
            Choice(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage(
                    content=content,
                    role="assistant",
                ),
            )
            for content in msgs
        ]
        mock_create.return_value = ChatCompletion(
            id="test",
            choices=choices,
            created=1,
            model="gpt-3.5-turbo",
            object="chat.completion",
        )

        chat = ChatOpenAIMultiGenerations(
            model="gpt-3.5-turbo", n=3, temperature=1, api_key="dummy"
        )
        got = chat.invoke("こんにちは！")
        print(got)
        self.assertEqual(len(got), 3)
