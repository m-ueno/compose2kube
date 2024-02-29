import marko
import marko.inline
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser


class MDCodeBlockOutputParser(StrOutputParser):
    def parse(self, text: str) -> str:
        if "```" not in text:
            return text
        if "```yaml" not in text:
            # Found the start of a code block (```), but the end is missing.
            # Then, just delete it.
            return text.replace("```", "")
        doc = marko.parse(text)
        for element in doc.children:
            if isinstance(element, marko.block.FencedCode):
                assert isinstance(element.children[0], marko.inline.RawText)
                return element.children[0].children
        raise ValueError("the text contains ``` but not match any codeblock" + text)
