import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from kubernetes import client, config
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Attempt to load kube config (assuming local minikube/kind setup)
try:
    config.load_kube_config()
    k8s_core = client.CoreV1Api()
    logger.info("Successfully loaded kubeconfig.")
except Exception as e:
    logger.error(f"Failed to load kubeconfig: {e}")
    k8s_core = None

class ReplRequest(BaseModel):
    repl_id: str
    stack: str = "node"

@app.post("/start")
async def start_repl(req: ReplRequest):
    if not k8s_core:
        raise HTTPException(status_code=500, detail="Kubernetes API not configured.")

    namespace = "default"
    pod_name = f"repl-{req.repl_id}"

    # 1. Create Pod
    # For Phase 1, we use a simple nginx image to prove we can orchestrate pods.
    # In Phase 2, this will be our custom runner image.
    pod_manifest = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            labels={"app": "runner", "repl_id": req.repl_id}
        ),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name="runner",
                    image=os.environ.get("RUNNER_IMAGE", "runner:latest"),
                    image_pull_policy="IfNotPresent",
                    ports=[client.V1ContainerPort(container_port=3000)]
                )
            ]
        )
    )

    try:
        k8s_core.create_namespaced_pod(namespace=namespace, body=pod_manifest)
        logger.info(f"Created Pod: {pod_name}")
    except client.exceptions.ApiException as e:
        if e.status == 409:
            logger.info(f"Pod {pod_name} already exists.")
        else:
            logger.error(f"Error creating Pod: {e}")
            raise HTTPException(status_code=500, detail="Failed to create Pod")

    # 2. Create Service
    service_name = f"svc-{req.repl_id}"
    service_manifest = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            labels={"app": "runner", "repl_id": req.repl_id}
        ),
        spec=client.V1ServiceSpec(
            selector={"repl_id": req.repl_id},
            ports=[client.V1ServicePort(port=80, target_port=3000)]
        )
    )

    try:
        k8s_core.create_namespaced_service(namespace=namespace, body=service_manifest)
        logger.info(f"Created Service: {service_name}")
    except client.exceptions.ApiException as e:
        if e.status == 409:
            logger.info(f"Service {service_name} already exists.")
        else:
            logger.error(f"Error creating Service: {e}")
            raise HTTPException(status_code=500, detail="Failed to create Service")

    return {"status": "created", "pod_name": pod_name, "service_name": service_name}
