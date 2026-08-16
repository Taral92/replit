import logging
import os
from typing import Dict, Optional

logger = logging.getLogger("WorkspaceK8sClient")

try:
    from kubernetes import client, config
    try:
        config.load_incluster_config()
    except Exception:
        try:
            config.load_kube_config()
        except Exception:
            pass
    k8s_core = client.CoreV1Api()
except Exception as e:
    k8s_core = None


class K8sWorkspaceProvisioner:
    """
    Provisions and manages dedicated Kubernetes Runner Pods per workspace.
    Enforces non-root security context, dropped capabilities, and resource limits.
    """

    def __init__(self, runner_image: Optional[str] = None):
        self.runner_image = runner_image or os.environ.get("RUNNER_IMAGE", "runner-ide/runner:v1.0.0")

    def create_workspace_pod(self, workspace_id: str, namespace: str = "default") -> Dict[str, str]:
        if not k8s_core:
            logger.warning("Kubernetes client not configured; operating in simulated mode.")
            return {
                "pod_name": f"runner-{workspace_id}",
                "service_name": f"svc-{workspace_id}",
                "namespace": namespace,
            }

        pod_name = f"runner-{workspace_id}"
        service_name = f"svc-{workspace_id}"

        # 1. Hardened Pod Specification
        pod_manifest = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=pod_name,
                namespace=namespace,
                labels={
                    "app": "runner",
                    "workspace_id": workspace_id,
                },
            ),
            spec=client.V1PodSpec(
                security_context=client.V1PodSecurityContext(
                    run_as_non_root=True,
                    run_as_user=1000,
                    fs_group=1000,
                ),
                containers=[
                    client.V1Container(
                        name="runner",
                        image=self.runner_image,
                        image_pull_policy="IfNotPresent",
                        ports=[
                            client.V1ContainerPort(name="http", container_port=3000),
                        ],
                        resources=client.V1ResourceRequirements(
                            limits={"cpu": "2", "memory": "2Gi"},
                            requests={"cpu": "500m", "memory": "512Mi"},
                        ),
                        security_context=client.V1SecurityContext(
                            allow_privilege_escalation=False,
                            read_only_root_filesystem=False,
                            capabilities=client.V1Capabilities(
                                drop=["ALL"],
                            ),
                        ),
                        volume_mounts=[
                            client.V1VolumeMount(
                                name="workspace-data",
                                mount_path="/workspace",
                            )
                        ],
                    )
                ],
                volumes=[
                    client.V1Volume(
                        name="workspace-data",
                        empty_dir=client.V1EmptyDirVolumeSource(),
                    )
                ],
                restart_policy="Never",
            ),
        )

        # 2. Workspace Service
        service_manifest = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=service_name,
                namespace=namespace,
                labels={"app": "runner", "workspace_id": workspace_id},
            ),
            spec=client.V1ServiceSpec(
                selector={"app": "runner", "workspace_id": workspace_id},
                ports=[client.V1ServicePort(port=80, target_port=3000)],
            ),
        )

        try:
            k8s_core.create_namespaced_pod(namespace=namespace, body=pod_manifest)
            k8s_core.create_namespaced_service(namespace=namespace, body=service_manifest)
            logger.info(f"Successfully provisioned Pod {pod_name} and Service {service_name}")
        except Exception as e:
            logger.error(f"Error provisioning K8s workspace: {e}")
            raise

        return {"pod_name": pod_name, "service_name": service_name, "namespace": namespace}

    def delete_workspace_pod(self, workspace_id: str, namespace: str = "default") -> bool:
        if not k8s_core:
            return True

        pod_name = f"runner-{workspace_id}"
        service_name = f"svc-{workspace_id}"
        try:
            k8s_core.delete_namespaced_pod(name=pod_name, namespace=namespace)
            k8s_core.delete_namespaced_service(name=service_name, namespace=namespace)
            return True
        except Exception as e:
            logger.error(f"Error deleting workspace pod: {e}")
            return False
