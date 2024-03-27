import glob
import os
from pathlib import Path
import unittest

import yaml

from compose2kube.benchmark.parser import MDCodeBlockOutputParser

parser = MDCodeBlockOutputParser()


class TestMDParser(unittest.TestCase):
    def test_parse_normalmd(self):
        input = want = """
apiVersion: v1
"""
        got = parser.parse(input)
        self.assertEqual(got, want)

    def test_parse(self):
        body = """
apiVersion: v1
"""
        cases = [
            # (input, want)
            (body, body),
            (f"```{body}```", body),
            (f"```yaml{body}```", body),
            (f"```plain{body}```", body),
            (f"```code{body}```", body),
            #
            # unclosed fence cases
            (f"```{body}", body),
            (f"{body}```", body),
            (f"```yaml{body}", body),
            # multi-fence cases
            (
                """
first:
```
a: 1
```

second:
```
b: 2
```
""",
                """a: 1
---
b: 2""",
            ),
        ]
        for i, (input, want) in enumerate(cases):
            with self.subTest(i=i):
                got = parser.parse(input)
                self.assertEqual(got.strip(), want.strip())

    def test_multiblock(self):
        input, want = (
            """
first:
```
aaa
```

second:
```
bbb
```
""",
            """aaa
---
bbb""",
        )
        got = parser.parse(input)
        got_parsed = list(yaml.safe_load_all(got))
        want_parsed = list(yaml.safe_load_all(want))
        self.assertListEqual(got_parsed, want_parsed)

    def test_keep_comments(self):
        input = """
```
# this is a comment
a: 1
```
"""
        got = parser.parse(input)
        want = """# this is a comment
a: 1
"""
        self.assertEqual(got, want)
        self.assertDictEqual(yaml.safe_load(got), yaml.safe_load(want))

    def test_can_parse_generated_text_without_exception(self):
        count = 0
        yaml_parse_failed = 0
        here = Path(os.path.dirname(__file__))
        for name in glob.glob(f"{here}/test_manifests/*.yaml"):
            with open(name) as f:
                yamls = parser.parse(f.read())
                count += 1
            try:
                _ = list(yaml.safe_load_all(yamls))
            except Exception:
                yaml_parse_failed += 1

        self.assertEqual(count, 100)
        self.assertLessEqual(yaml_parse_failed, 2)
