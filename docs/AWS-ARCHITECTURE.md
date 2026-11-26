# AWS EKS architecture (ap-south-1, 2026-11-26)

Provisioned with Terraform (`infra/aws`). 56 resources, plus things Kubernetes creates later.

## Request flow (browser to database)

1. Browser resolves the ELB hostname (a6f1ae8c...ap-south-1.elb.amazonaws.com).
2. Classic ELB (internet-facing, public subnets, created by the `frontend` LoadBalancer service) forwards to NodePort 30249 on a worker node.
3. Worker node (private subnet) kube-proxy routes to the frontend pod on port 8080.
4. frontend calls:
   - userservice: login, issues JWT, reads accounts-db
   - contacts: reads accounts-db
   - balancereader, transactionhistory: read ledger-db
   - ledgerwriter: writes ledger-db (validates the JWT with the jwt-key public key)
5. accounts-db and ledger-db store data on encrypted gp3 EBS volumes (PVCs).
6. loadgenerator continuously creates transactions, so history is never empty.

Outbound: node, NAT gateway, internet gateway, GHCR (image pulls). Nodes have no public IPs and nothing can reach them directly from the internet.

## Resources and purpose

| Resource | Value | Purpose |
|---|---|---|
| VPC | bank-eks-vpc, 10.0.0.0/16 (vpc-058ea399d9b84c681) | Isolated network |
| Public subnets | 10.0.101.0/24 (1a), 10.0.102.0/24 (1b) | Load balancer, NAT gateway |
| Private subnets | 10.0.1.0/24 (1a), 10.0.2.0/24 (1b) | Worker nodes |
| Internet gateway | 1 | Public subnet internet route |
| NAT gateway | nat-07809afc650fdff5d (public 1a) | Outbound-only internet for nodes. Main cost driver |
| EKS control plane | bank-eks, Kubernetes 1.34 | Managed API server, scheduler, etcd |
| Worker nodes | 2 x m7i-flex.large (1a, 1b) | Run the pods. t3.medium is blocked on the free plan |
| Security groups | cluster + node | Firewall between control plane, nodes, ELB |
| IAM roles | cluster, node | EKS management, CNI, image pulls, EBS CSI |
| KMS key | 1 | Encrypts Kubernetes Secrets at rest |
| OIDC provider | 1 | Lets pods assume IAM roles (IRSA) for later tools |
| EBS CSI addon + gp3 StorageClass | default class | Creates encrypted EBS disks for PVCs |
| EBS volumes | vol-07fe229a1f34bf50e, vol-05cfb97087312b295 (1 GiB gp3, encrypted) | accounts-db, ledger-db data |
| Classic ELB | a6f1ae8c2cf664862a6933211b2c2663, internet-facing | Public entry point (created by Kubernetes) |
| CloudWatch log group | 1 | Control plane logs |

Cost while running: about $0.25 to $0.30 per hour (control plane $0.10, NAT, 2 nodes).

## Not in Terraform (created by Kubernetes)

ELB and EBS volumes. They must be deleted before `terraform destroy`, or the VPC deletion hangs.

## Manual steps on a fresh cluster (to automate later)

- Secrets: ledger-db-secret, accounts-db-secret, jwt-key
- gp3 default StorageClass
- PGDATA=/var/lib/postgresql/data/pgdata on both DB StatefulSets (EBS root is owned by root)
