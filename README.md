# RunnerIDE

RunnerIDE is a cloud-native, scalable Integrated Development Environment (IDE) built on Kubernetes. It dynamically provisions isolated development workspaces for users, providing real-time terminal access and file synchronization directly in the browser.

## Architecture Overview

The system is designed with a microservices architecture, utilizing cloud-native patterns to ensure isolation, security, and scalability.

1. **Orchestrator API (Python/FastAPI)**
   - Acts as the control plane for the platform.
   - Interfaces directly with the Kubernetes API to dynamically spin up isolated Workspace Pods on-demand.
   - Manages lifecycle and routing assignments for user workspaces.

2. **Workspace Runner (Node.js/Socket.io)**
   - The isolated execution environment deployed for each user.
   - Runs a WebSocket server that provides real-time access to a pseudo-terminal (`node-pty`) and the filesystem.

3. **Client UI (React/Vite)**
   - A lightweight frontend interface providing terminal emulation (`xterm.js`).
   - Connects securely to the user's isolated workspace via Kubernetes Ingress routing.

4. **Infrastructure (Terraform/AWS EKS)**
   - Fully automated infrastructure as code.
   - Provisions an AWS EKS cluster, VPC, and ECR container registries for production deployment.

## CI/CD Pipeline

The project utilizes GitHub Actions for continuous integration and continuous deployment (CI/CD):
- Automatically builds the Orchestrator and Runner Docker images.
- Pushes artifacts to Amazon ECR.
- Deploys updated Kubernetes manifests (`Deployment`, `Service`, `Ingress`) to the live AWS EKS cluster.

## Getting Started

### Prerequisites
- Docker
- Kubernetes (Minikube or AWS EKS)
- Terraform (for cloud deployment)

### Local Development
1. Start a local Kubernetes cluster (e.g., `minikube start`).
2. Build the Workspace Runner Docker image locally.
3. Start the FastAPI Orchestrator service.
4. Run the Vite React frontend.
