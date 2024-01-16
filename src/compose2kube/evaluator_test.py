import unittest

from compose2kube import evaluator, templates


class TestChain(unittest.TestCase):
    def test_ops(self):
        evaluator.ops.get_graph().print_ascii()
        assert True

    def test_chain(self):
        evaluator.convert_chain.invoke("")

    def test_template(self):
        chain = {
            "input": lambda _: "THISISINPUT",
            "target": lambda _: "TARGET",
        } | templates.prompt_zeroshot
        got = chain.invoke({})
        self.assertTrue(got)

        got2 = templates.prompt_zeroshot.invoke(
            {
                "input": "THISISINPUT",
                "target": "TARGET",
            }
        )
        self.assertTrue(got)
