
## 11. Fast rebuild (supersedes sections 3 and 4)
```bash
cd infra/aws
terraform init
terraform apply -var 'console_principal_arn=arn:aws:iam::<account-id>:root'
aws eks update-kubeconfig --region ap-south-1 --name bank-eks
kubectl config current-context            # must be the EKS context
scripts/create-secrets.sh bank-eks        # ledger-db, accounts-db, jwt-key (+ Slack/LLM if monitoring ns exists)
kubectl apply -k deploy/overlays/eks      # app + gp3 StorageClass + PGDATA patch
kubectl get pods
```
- The EKS overlay replaces the manual gp3 StorageClass and the PGDATA `kubectl set env` fix.
- The console access entry is now in Terraform (`console_principal_arn`), so the EKS console Resources tab works from the start.
- On kind, deploy with `kubectl apply -k kubernetes-manifests` (plain `apply -f` fails on kustomization.yaml).
- Cleanup order is unchanged (section 7): `kubectl delete -k deploy/overlays/eks`, delete PVCs, wait for the ELB and volumes to vanish, then `terraform destroy`.
