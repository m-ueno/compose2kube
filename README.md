# compose2kube

Experiment code to synthesis Kubernetes manifests from compose specifications using LLMs.

## Description

- `dataset/`: Contains additional files and resources related to the project.
- `notebooks/`: Contains Jupyter notebooks for running benchmarks.
- `src/`: Contains the source code for the project.
    - [src/compose2kube/benchmark/grader/rule.py](src/compose2kube/benchmark/grader/rule.py) : micro-benchmark rules
    - [src/compose2kube/benchmark/grader/llm.py](src/compose2kube/benchmark/grader/llm.py) : context-groundedness evaluation prompt

## Running benchmarks

### Requirements

- Python>=3.10
- Poetry>=1.8.3
- `OPENAI_API_KEY`

```shell
$ poetry install
open notebooks/*.ipynb and run
```
