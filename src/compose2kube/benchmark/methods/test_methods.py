import unittest
from subprocess import check_output
from unittest.mock import MagicMock, patch

from langchain_core.pydantic_v1 import BaseModel
from langchain_core.runnables import RunnableConfig
from langchain_openai.chat_models import ChatOpenAI

from compose2kube.benchmark.methods import (
    Document,
    canonicalize,
    chain_zeroshottext,
    kompose,
)

compose1 = """services:
    web:
        image: nginx:latest
        ports:
            - "80:80"
"""


mocked_response = {
    "id": "chatcmpl-7fcZavknQda3SQ",
    "object": "chat.completion",
    "created": 1689989000,
    "model": "gpt-3.5-turbo-0613",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Bar Baz",
                "name": "Erick",
            },
            "finish_reason": "stop",
        }
    ]
    * 2,
}


class TestMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # because cache=True is hard-coded, we need to setup cache
        from langchain.cache import SQLiteCache
        from langchain.globals import set_llm_cache

        set_llm_cache(SQLiteCache(":memory:"))

    def test_canonicalize(self):
        got = canonicalize.invoke(Document(page_content=compose1))
        self.assertEqual(got.metadata.get("stderr"), "")
        print("content:", got.page_content)

    def test_kompose(self):
        # short compose file
        doc = Document(page_content=compose1)
        got = kompose.invoke(doc)
        self.assertEqual(got.metadata.get("stderr"), "")
        print("kompose:", got.page_content)

    def test_kompose_version(self):
        got = check_output("kompose version", shell=True, text=True)
        self.assertGreaterEqual(got, "1.31.0")

    @patch("openai.resources.chat.completions.Completions.create")
    def test__how_to_use_patch(self, mock_create):
        mock_create.return_value = mocked_response
        from langchain_core.output_parsers import StrOutputParser

        chain = ChatOpenAI() | StrOutputParser()
        got = chain.invoke("Hello, world!")
        self.assertEqual(got, "Bar Baz")

    @patch("openai.resources.chat.completions.Completions.create")
    def test_parser(self, mock_create):
        mock_create.return_value = mocked_response
        from compose2kube.benchmark.parser import MDCodeBlockOutputParser

        chain = ChatOpenAI() | MDCodeBlockOutputParser()
        got = chain.invoke("yo hoho")
        self.assertEqual(got, "Bar Baz")

    # @patch("openai.resources.chat.chat.Chat.completions")
    # @patch("langchain_openai.chat_models.ChatOpenAI.client")
    # @patch("compose2kube.model.ChatOpenAIMultiGenerations.invoke") # ok but too near
    # @patch("langchain_openai.ChatOpenAI.client") # pydantic fails?
    @patch("openai.resources.chat.completions.Completions.create")
    def test_chain_zeroshottext(self, mock_create):
        mock_create.return_value = mocked_response

        n = 2
        got = chain_zeroshottext.invoke(
            Document(page_content=compose1), config=RunnableConfig(n=n, cache=True)
        )
        self.assertEqual(len(got), n)
        self.assertIsInstance(got[0], Document)
        # self.assertTrue(hasattr(got[0], 'page_content'))
        # self.assertTrue(hasattr(got[0], 'metadata'))
        self.assertIn("output_str", got[0].metadata)
