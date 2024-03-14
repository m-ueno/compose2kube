from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.runnables import (
    ConfigurableField,
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
)
from langchain_openai import ChatOpenAI

prompt_grader = ChatPromptTemplate.from_messages(
    messages=[
        SystemMessagePromptTemplate.from_template(
            """Your primary concern is making sure that given the compose file, the generated kubernetes manifests are correct."""
        ),
        HumanMessagePromptTemplate.from_template(
            """
Judge if kubernetes manifests are correctly converted from the given compose file.
If correct then the decision is 'Y' otherwise 'N'.
Separate the decision and the explanation. For example:
{
    "decision": "Y",
    "explanation": "..."
}

####Manifest####

{{ manifest }}

####Compose####

{{ compose }}""",
            template_format="jinja2",
        ),
    ],
)

# receive {compose, manifest}
chain_grader = (
    prompt_grader
    | ChatOpenAI(cache=True, model_kwargs={"seed": 1}, temperature=0)
    .configurable_fields(model_name=ConfigurableField(id="grader_model_name"))
    .with_retry()
    | JsonOutputParser(name="grader parser").with_fallbacks(
        [RunnableLambda(lambda _: {"decision": "N", "explanation": "parse failed"})]
    )
).with_config(run_name="chain_grader")
