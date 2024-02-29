import unittest
from subprocess import check_output
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from compose2kube.benchmark.methods import Document, canonicalize, kompose  # noqa: E402

compose1 = """services:
    web:
        image: nginx:latest
        ports:
            - "80:80"
"""


class TestMethods(unittest.TestCase):
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
