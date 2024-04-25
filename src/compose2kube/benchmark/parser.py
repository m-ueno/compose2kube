import warnings

import marko
import marko.inline
from langchain_core.output_parsers import StrOutputParser


class MDCodeBlockOutputParser(StrOutputParser):
    def parse(self, text: str) -> str:
        match text.count("```"):
            case 0:
                return text
            case 1:
                # skip the line contains ```
                return "\n".join(line for line in text.split("\n") if "```" not in line)
            case 2:
                doc = marko.parse(text)
                for element in doc.children:
                    if isinstance(element, marko.block.FencedCode):
                        assert isinstance(element.children[0], marko.inline.RawText)
                        return element.children[0].children
                raise Exception("fenced code not found")
            case x if x % 2 == 0:
                doc = marko.parse(text)
                codes = []
                for element in doc.children:
                    if isinstance(element, marko.block.FencedCode):
                        blockchild = element.children[0]
                        assert isinstance(blockchild, marko.inline.RawText)
                        codes.append(blockchild.children.strip())
                return "\n---\n".join(codes)
            case x if x % 2 == 1:
                warnings.warn("the text contains odd number of ```:" + text)
                return ""

        raise Exception("must not reach here")
