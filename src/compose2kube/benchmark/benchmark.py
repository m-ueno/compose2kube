from operator import attrgetter, itemgetter

import yaml
from langchain.chains.openai_functions import convert_to_openai_function, get_openai_output_parser
from langchain.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    ConfigurableField,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_core.runnables import (
    chain as chain_decorator,
)

from compose2kube.benchmark.grader import chains_grade
from compose2kube.benchmark.grader.rule import INPUTS_JUDGES
from compose2kube.benchmark.methods import CONVERT_METHODS, to_doc
from compose2kube.benchmark.parser import MDCodeBlockOutputParser
from compose2kube.evaluator import Manifests
from compose2kube.model import ChatOpenAIMultiGenerations


def _join_manifests(xs: list[dict | str]) -> str:
    # compose.llm.Manifests.manifests: list[str|dict] にした結果のその場しのぎの関数
    child = xs[0]
    if isinstance(child, dict):
        return yaml.safe_dump_all(xs)
    elif isinstance(child, str):
        return "\n---\n".join(xs)  # type:ignore
    else:
        raise ValueError(f"argument must be list[dit|str]: {xs}")


@chain_decorator
def dedoc(doc: Document) -> str:
    return doc.page_content


# さまざまなメソッドからなるチェーン
# receive {compose, judge}
chains_convert_grade = RunnableParallel(
    #
    # Method1
    #
    zeroshot_txt=RunnablePassthrough.assign(
        output={"compose": itemgetter("compose")}
        | PromptTemplate.from_template(
            "convert the composefile to kubernetes manifests:\n{compose}"
        )
        | ChatOpenAIMultiGenerations(cache=True, model_kwargs={"seed": 1}).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            n=ConfigurableField(id="n", name="llm_n"),
        )
    )
    .assign(  # {compose, judge, output}
        output_str=itemgetter("output") | StrOutputParser().map(),
        output_parsed=itemgetter("output") | MDCodeBlockOutputParser().map(),
    )
    .pick(["compose", "judge", "output", "output_str", "output_parsed"])
    | chains_grade,
    #
    # Method2: JSON mode
    #
    zeroshot_jsonmode=RunnablePassthrough.assign(
        output={"compose": itemgetter("compose")}
        | PromptTemplate.from_template(
            "convert the composefile to kubernetes manifests:\n{{compose}}",
            template_format="jinja2",
        )
        | ChatOpenAIMultiGenerations(
            cache=True,
            model_kwargs={
                "seed": 1,
                "functions": [convert_to_openai_function(Manifests)],
                "function_call": {"name": "Manifests"},
            },
        ).configurable_fields(
            model_name=ConfigurableField(id="model_name"),
            n=ConfigurableField(id="n", name="llm_n"),
        )
    )
    .assign(  # {compose, judge, output}
        output_parsed=itemgetter("output")
        | (get_openai_output_parser([Manifests]) | (lambda m: m.manifests) | _join_manifests)
        .with_fallbacks([RunnableLambda(lambda _: "parse failed")])
        .map(),
    )
    .pick(["compose", "judge", "output", "output_parsed"])
    | chains_grade,
    #
    # Method3: annotate -> kompose
    # annotate_kompose=RunnablePassthrough.assign(
    #     output_with_metadata=itemgetter("compose")
    #     | to_doc
    #     | CONVERT_METHODS["annotate_kompose"],
    # )
    # .assign(
    #     output_parsed=itemgetter("output_with_metadata")
    #     | RunnableLambda(lambda doc: doc.page_content).map()
    # )
    # .pick(["compose", "judge", "output_with_metadata", "output_parsed"])
    # | chains_grade,
    # #
    # # Method4: 正規化してからmethod3
    # canonicalize_annotate_kompose=RunnablePassthrough.assign(
    #     output_with_metadata=itemgetter("compose")
    #     | to_doc
    #     | CONVERT_METHODS["canonical_annotate_kompose"],
    # )
    # .assign(
    #     output_parsed=itemgetter("output_with_metadata")
    #     | RunnableLambda(lambda doc: doc.page_content).map()
    # )
    # .pick(["compose", "judge", "output_with_metadata", "output_parsed"])
    # | chains_grade,
    #
    # Method5: expert prompting
    #
    expertprompting_text=RunnablePassthrough.assign(
        output_parsed=itemgetter("compose")
        | to_doc
        | CONVERT_METHODS["expertprompting_text"]  # receives Document
        | dedoc.map()  # TODO: make chains_grade accept Document, not str
    ).pick(["compose", "judge", "output", "output_parsed"])
    | chains_grade,
    # Method5' expert prompting (JSON mode)
    expertprompting_json=RunnablePassthrough.assign(
        output_parsed=itemgetter("compose")
        | to_doc
        | CONVERT_METHODS["expertprompting_json"]
        | dedoc.map()
    ).pick(["compose", "judge", "output", "output_parsed"])
    | chains_grade,
)
