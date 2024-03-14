import json
from dataclasses import dataclass
from operator import itemgetter
from typing import Any

from langchain_core.runnables import RunnablePassthrough

from .dryrun import dryrun_str
from .llm import chain_grader


@dataclass
class Judgement:
    ok: bool
    metadata: dict[str, Any]

    def to_json(self, *args, **kwargs):
        return json.dumps(self.__dict__)


# 複数の評価 (Correctness, groundness) をするチェーン
# receive {compose, judge, output_parsed}
chains_grade = RunnablePassthrough.assign(
    grade_by_function=lambda dic: list(map(dic["judge"], dic["output_parsed"])),  # type: ignore
    grade_by_model=RunnablePassthrough.assign(
        _in_out_pairs=lambda dic: [
            {"compose": dic["compose"], "manifest": m} for m in dic["output_parsed"]
        ]
    ).assign(model_graded=itemgetter("_in_out_pairs") | chain_grader.map()),
    grade_by_dryrun=itemgetter("output_parsed") | dryrun_str.map(),
)
