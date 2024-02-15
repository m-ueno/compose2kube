import unittest
from unittest.mock import patch

from compose2kube.model import ChatOpenAIMultiGenerations


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
