# 1. VPC Configuration
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "${var.cluster_name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
  
  # Tags required by EKS
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

# 2. EKS Cluster
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.28"

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.public_subnets

  # Public access required for GitHub Actions to deploy
  cluster_endpoint_public_access  = true

  eks_managed_node_groups = {
    default = {
      min_size     = 1
      max_size     = 3
      desired_size = 2

      instance_types = ["t3.medium"]
    }
  }
}

# 3. ECR Repositories for our images
resource "aws_ecr_repository" "orchestrator" {
  name                 = "runner-ide/orchestrator"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_repository" "runner" {
  name                 = "runner-ide/runner"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

# Outputs for CI/CD
output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}
output "orchestrator_repo_url" {
  value = aws_ecr_repository.orchestrator.repository_url
}
output "runner_repo_url" {
  value = aws_ecr_repository.runner.repository_url
}
