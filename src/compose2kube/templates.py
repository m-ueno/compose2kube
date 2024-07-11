import inspect
import unittest

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, BasePromptTemplate

prompt1_for_kompose = ChatPromptTemplate.from_messages(
    [
        # (
        #     "system",
        #     "You are a skillful devops engineer.",
        # ),
        (
            "human",
            inspect.cleandoc(
                """
            Please annotate the input compose file with appropriate labels for Kompose.

            The output from Kompose will later be deployed to an {target} environment.
            Be sure to apply labels that will allow it to function properly in the deployment environment.

            if you want inform us something, make it inline comment inside yaml.

            ###References###

            here are storageclasses in the target environment:
            ---
            apiVersion: storage.k8s.io/v1
            kind: StorageClass
            metadata:
            name: efs-sc
            provisioner: efs.csi.aws.com
            ---

            kompose supports Kompose-specific labels within the docker-compose.yml file to explicitly define the generated resources’ behavior upon conversion, like Service, PersistentVolumeClaim…

The currently supported options are:

Key	Value
kompose.service.type	nodeport / clusterip / loadbalancer / headless
kompose.service.group	name to group the containers contained in a single pod
kompose.service.expose	true / hostnames (separated by comma)
kompose.service.nodeport.port	port value (string)
kompose.service.expose.tls-secret	secret name
kompose.service.expose.ingress-class-name	ingress class name
kompose.volume.size	kubernetes supported volume size
kompose.volume.storage-class-name	kubernetes supported volume storageClassName
kompose.volume.type	use k8s volume type, eg “configMap”, “persistentVolumeClaim”, “emptyDir”, “hostPath”
kompose.controller.type	deployment / daemonset / replicationcontroller / statefulset
kompose.image-pull-policy	kubernetes pods imagePullPolicy
kompose.image-pull-secret	kubernetes secret name for imagePullSecrets
kompose.service.healthcheck.readiness.disable	kubernetes readiness disable
kompose.service.healthcheck.readiness.test	kubernetes readiness exec command
kompose.service.healthcheck.readiness.http_get_path	kubernetes readiness httpGet path
kompose.service.healthcheck.readiness.http_get_port	kubernetes readiness httpGet port
kompose.service.healthcheck.readiness.tcp_port	kubernetes readiness tcpSocket port
kompose.service.healthcheck.readiness.interval	kubernetes readiness interval value
kompose.service.healthcheck.readiness.timeout	kubernetes readiness timeout value
kompose.service.healthcheck.readiness.retries	kubernetes readiness retries value
kompose.service.healthcheck.readiness.start_period	kubernetes readiness start_period
kompose.service.healthcheck.liveness.http_get_path	kubernetes liveness httpGet path
kompose.service.healthcheck.liveness.http_get_port	kubernetes liveness httpGet port
kompose.service.healthcheck.liveness.tcp_port	kubernetes liveness tcpSocket port
kompose.service.external-traffic-policy	‘cluster’, ‘local’, ‘’
kompose.security-context.fsgroup	kubernetes pod security group fsgroup
kompose.volume.sub-path	kubernetes volume mount subpath
            """
            ),
        ),
        (
            "human",
            "Make calls to the relevant function to record the entities in the following input: ```{input}```",
        ),
        ("human", "Tip: Make sure to answer in the correct format"),
    ]
)

prompt_zeroshot = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a skillful devops engineer. Please output kubenetes manifest corresponding to the given files.",
        ),
        (
            "human",
            "Make calls to the relevant function to record the entities in the following input: ```{input}```",
        ),
        ("human", "Tip: Make sure to answer in the correct format"),
        (
            "human",
            inspect.cleandoc(
                """Note: Make sure the output manifests work in {target} environment.

            if you want inform us something, make it inline comment inside yaml.

            ###REFERENCE###
            here are storageclasses in the target environment:
            ---
            apiVersion: storage.k8s.io/v1
            kind: StorageClass
            metadata:
            name: efs-sc
            provisioner: efs.csi.aws.com
            ---
            """
            ),
        ),
    ]
)

"""
            # Output the following kube resources:
            # - Service
            # - Deployment
            # - PVC (if necessary)
"""


prompt_eval_manifests_create = """You are a skillful devops engineer. Please evaluate the following manifests.

####manifest####
{manifest}

####Reference####
{reference}
"""


# prompt_fewshot = PromptTemplate.from_template(
#     """You are a skillful devops engineer. Please output kubenetes manifest corresponding to the given files.

# Make sure to answer in the correct format.
# If you want inform users something, make it inline comment inside yaml.

# The provided examples are for illustration purposes only and should not be repeated.
# **EXAMPLES**
# {{EXAMPLES}}

# **INPUT**
# {{compose}}
# """,
#     template_format="jinja2",
# )

template_fewshot = PromptTemplate.from_template(
    """You are a skillful devops engineer. Please output kubenetes manifest corresponding to the given files.
Make sure to answer in the correct format.
If you want inform users something, make it inline comment inside yaml.

The provided examples are for illustration purposes only and should not be repeated.

###EXAMPLES###
{{examples}}

###END OF EXAMPLES###

###INPUT###
{{compose}}

###OUTPUT###
    """,
    template_format="jinja2",
    # partial_variables={"examples": examples},
)


def make_prompt_fewshot_outputonly(outputs: list[str]) -> BasePromptTemplate:
    """Return a augmented prompt template that accepts 'compose'"""

    examples = ""
    for i, output in enumerate(outputs):
        examples += f"###Example output {i}###\n"
        examples += output.strip() + "\n\n"

    return template_fewshot.partial(examples=examples)
    return PromptTemplate.from_template(
        """You are a skillful devops engineer. Please output kubenetes manifest corresponding to the given files.
Make sure to answer in the correct format.
If you want inform users something, make it inline comment inside yaml.

The provided examples are for illustration purposes only and should not be repeated.

###EXAMPLES###
{{examples}}

###END OF EXAMPLES###

###INPUT###
{{compose}}

###OUTPUT###
    """,
        template_format="jinja2",
        partial_variables={"examples": examples},
    )


def make_prompt_fewshot(outputs: list[str], inputs: list[str] | None) -> BasePromptTemplate:
    """Return a augmented prompt template that accepts 'compose'"""

    if inputs is None:
        return make_prompt_fewshot_outputonly(outputs)

    examples = ""
    for i, (input, output) in enumerate(zip(inputs, outputs)):
        examples += f"###Example input {i+1}###\n"
        examples += input.strip() + "\n\n"
        examples += f"###Example output {i+1}###\n"
        examples += output.strip() + "\n\n"

    return template_fewshot.partial(examples=examples)
