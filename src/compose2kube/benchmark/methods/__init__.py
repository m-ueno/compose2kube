import subprocess
import tempfile
from logging import getLogger
from operator import itemgetter
from typing import List, cast

from langchain.prompts import PromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (
    ConfigurableField,
    RunnableLambda,  # noqa: F401
    RunnableParallel,
    RunnablePassthrough,
    RunnableSerializable,
)
from langchain_core.runnables import (
    chain as chain_decorator,
)
from langchain_openai import ChatOpenAI

from compose2kube import templates
from compose2kube.benchmark.parser import MDCodeBlockOutputParser
from compose2kube.model import ChatOpenAIMultiGenerations

logger = getLogger(__name__)


@chain_decorator
def canonicalize(spec: Document) -> Document:
    """return stdout and stderr separately of command `docker compose config`"""
    with tempfile.NamedTemporaryFile(
        "w", prefix="canonicalize", suffix=".yaml", delete=False
    ) as tmp:
        tmp.write(spec.page_content)
        tmp.close()
        logger.debug(tmp.name)

        # get stdout and stderr separately using pipe
        with subprocess.Popen(
            f"docker compose -f {tmp.name} config --no-path-resolution --no-interpolate",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        ) as proc:
            stdout, stderr = proc.communicate()
            return Document(page_content=stdout, metadata=dict(stderr=stderr))


@chain_decorator
def kompose(spec: Document) -> Document:
    """return output of command `kompose convert`"""
    with tempfile.NamedTemporaryFile(
        "w", prefix="kompose", suffix=".yaml", delete=False
    ) as tmp:
        tmp.write(spec.page_content)
        tmp.close()
        logger.debug(tmp.name)

        with subprocess.Popen(
            f"kompose convert -f {tmp.name} --stdout",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        ) as proc:
            stdout, stderr = proc.communicate()
            return Document(
                page_content=stdout, metadata=dict(stderr=stderr, orig_spec=spec)
            )


@chain_decorator
def to_doc(page_content: str, **kwargs) -> Document:
    return Document(page_content=page_content, **kwargs)


# receive Document, return Documents
chain_annotate: RunnableSerializable[Document, list[Document]] = (
    {"input": lambda doc: doc.page_content, "target": lambda _: "AWS EKS"}
    | templates.prompt1_for_kompose
    | ChatOpenAIMultiGenerations(
        cache=True, model_kwargs={"seed": 1}
    ).configurable_fields(
        n=ConfigurableField(id="annotate_n"),
        model_name=ConfigurableField(id="annotate_model_name"),
    )
    | (MDCodeBlockOutputParser() | to_doc).map()
)

chain_annotate_kompose = chain_annotate | kompose.map()
chain_canonical_annotate_kompose = canonicalize | chain_annotate | kompose.map()

#
# [2305.14688] ExpertPrompting: Instructing Large Language Models to be Distinguished Experts
# https://arxiv.org/abs/2305.14688
prompt_expert_identity = PromptTemplate.from_template("""
For each instruction, write a high-quality description about the most capable
and suitable agent to answer the instruction. In second person perspective.

[Instruction]: Make a list of 5 possible effects of deforestation.
[Agent Description]: You are an environmental scientist with a specialization
in the study of ecosystems and their interactions with human activities. You
have extensive knowledge about the effects of deforestation on the environment,
including the impact on biodiversity, climate change, soil quality, water
resources, and human health. Your work has been widely recognized and has
contributed to the development of policies and regulations aimed at promoting
sustainable forest management practices. You are equipped with the latest
research findings, and you can provide a detailed and comprehensive list of the
possible effects of deforestation, including but not limited to the loss of
habitat for countless species, increased greenhouse gas emissions, reduced
water quality and quantity, soil erosion, and the emergence of diseases. Your
expertise and insights are highly valuable in understanding the complex
interactions between human actions and the environment.

[Instruction]: Identify a descriptive phrase for an eclipse.
[Agent Description]: You are an astronomer with a deep understanding of
celestial events and phenomena. Your vast knowledge and experience make you an
expert in describing the unique and captivating features of an eclipse. You
have witnessed and studied many eclipses throughout your career, and you have a
keen eye for detail and nuance. Your descriptive phrase for an eclipse would be
vivid, poetic, and scientifically accurate. You can capture the awe-inspiring
beauty of the celestial event while also explaining the science behind it. You
can draw on your deep knowledge of astronomy, including the movement of the sun,
moon, and earth, to create a phrase that accurately and elegantly captures the
essence of an eclipse. Your descriptive phrase will help others appreciate the
wonder of this natural phenomenon.

[Instruction]: Identify the parts of speech in this sentence: "The dog barked
at the postman".
[Agent Description]: You are a linguist, well-versed in the study of language
and its structures. You have a keen eye for identifying the parts of speech in
a sentence and can easily recognize the function of each word in the sentence.
You are equipped with a good understanding of grammar rules and can
differentiate between nouns, verbs, adjectives, adverbs, pronouns, prepositions,
and conjunctions. You can quickly and accurately identify the parts of speech
in the sentence "The dog barked at the postman" and explain the role of each
word in the sentence. Your expertise in language and grammar is highly valuable
in analyzing and understanding the nuances of communication.

[Instruction]: {question}
[Agent Description]:
""")

prompt_expertprompting = PromptTemplate.from_template("""{expert_identity}

Now given the above identity background, please answer the following instruction:

{question}""")

#
# 前処理なし
#
prompt_zeroshot = PromptTemplate.from_template(
    "convert the composefile to kubernetes manifests:\n{compose}"
)

chain_zeroshottext = (
    {"compose": lambda doc: doc.page_content}
    | prompt_zeroshot
    | ChatOpenAIMultiGenerations(
        cache=True, model_kwargs={"seed": 1}
    ).configurable_fields(
        n=ConfigurableField(id="n"), model_name=ConfigurableField(id="model_name")
    )
    | (MDCodeBlockOutputParser() | to_doc).map()
)


# input is a Document
chain_expert_prompting: RunnableSerializable[Document, List[Document]] = (
    RunnableParallel(
        compose=RunnableLambda(lambda doc: cast(Document, doc).page_content),
    )
    .assign(
        expert_identity=(
            {"question": lambda _: "convert the composefile to kubernetes manifests"}
            | prompt_expert_identity
            | ChatOpenAI(cache=True, model_kwargs={"seed": 1})
            | StrOutputParser()
        ),
        question={"compose": itemgetter("compose")}
        | prompt_zeroshot
        | (lambda p: p.to_string()),
    )
    .pick(["expert_identity", "question"])
    | prompt_expertprompting
    | ChatOpenAIMultiGenerations(
        cache=True, model_kwargs={"seed": 1}
    ).configurable_fields(
        model_name=ConfigurableField(id="model_name"),
        n=ConfigurableField(id="n", name="llm_n"),
    )
    | (MDCodeBlockOutputParser() | to_doc).map()
)

#
# input is a Document, output is a List[Document]
CONVERT_METHODS = dict(
    annotate_kompose=chain_annotate_kompose,
    canonical_annotate_kompose=chain_canonical_annotate_kompose,
    zeroshottext=chain_zeroshottext,
    expertprompting_text=chain_expert_prompting,
)
