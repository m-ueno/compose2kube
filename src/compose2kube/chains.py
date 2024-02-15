from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda,
)
from compose2kube.llm import Manifests
from compose2kube.templates import prompt1_for_kompose, prompt_zeroshot
from compose2kube.evaluator import (
    convert_by_kompose,
    convert_by_llm,
    enrich_by_llm,
)

convert_chain = RunnableParallel(
    kompose=convert_by_kompose | list,
    llm={"input": lambda x: x, "target": lambda _: "AWS EKS"}
    | prompt_zeroshot
    | convert_by_llm
    | RunnableLambda(
        lambda ms: ms.manifests if isinstance(ms, Manifests) else []
    ).map(),
)
