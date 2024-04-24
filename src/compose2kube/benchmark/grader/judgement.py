import json
from dataclasses import dataclass
from typing import Any


@dataclass
class Judgement:
    ok: bool
    metadata: dict[str, Any]

    def to_json(self, *args, **kwargs):
        return json.dumps(self.__dict__)
