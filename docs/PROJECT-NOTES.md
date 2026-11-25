# bank-platform: Project Notes

Repo: github.com/shanthipocha/bank-platform (public), based on Bank of Anthos
Last updated: 2026-11-25
Environment: Windows + WSL2 Ubuntu, Docker Desktop, kind cluster `bank`, JDK 17 in WSL

Sections marked (from summary) came from an earlier session and were not re-verified.

## 1. Status at a glance

| Area | State |
|---|---|
| App on kind | Running, payments and transfers verified in browser |
| Incident fixes (tracing, DB data loss) | Done (from summary) |
| DB hardening (non-root, readOnlyRootFilesystem) | Done, verified (from summary) |
| CI: secrets, config, fs scans | gitleaks, trivy fs/config (from summary) |
| CI: Python services | Build, scan, gate, push to GHCR (from summary) |
| CI: Java services | Done this session, matrix workflow, all 3 green |
| Manifests -> own GHCR images | Done, 7 of 9 images |
| Dependabot | Enabled (from summary) |
| AWS / Azure / GCP | Not started |

## 2. Timeline of what was done

### Earlier sessions (from summary)
- Got Bank of Anthos running on kind cluster `bank`.
- Fixed incidents: tracing problem; DB data loss, fixed by adding PVCs.
- Hardened accounts-db and ledger-db: non-root user, readOnlyRootFilesystem, verified.
- Built CI:
  - gitleaks (secret scanning)
  - trivy fs and config scan (`security.yml`)
  - Python matrix workflow (`build-python-services.yml`): frontend, userservice, contacts, loadgenerator. Flow: build -> scan -> gate (fixable CRITICAL) -> push to GHCR tagged by commit SHA.
  - Balancereader workflow (was report-only, no gate).
- Enabled Dependabot.

### This session (2026-11-25)

1. Java local build and scan (balancereader)
   - Build: `./mvnw -pl src/ledger/balancereader -am compile jib:dockerBuild -Djib.to.image=balancereader-local`
   - Jib credential-helper warnings are harmless (anonymous base image pull).
   - Trivy not installed in WSL, so run it via Docker with a cache volume and longer timeout (first run needs the Java DB download, about 3 minutes, and the default 5m timeout failed):
     `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ aquasec/trivy:latest image --timeout 15m --skip-version-check --severity HIGH,CRITICAL --ignore-unfixed <image>`

2. Root cause of leftover Java CVEs
   - The jackson-bom property (2.22.3) was set, but `jackson-databind` (2.22.2) and `guava` (33.7.1-jre) were hardcoded in each service pom's `<dependencies>` block, overriding the BOM.
   - Fix in all three poms (balancereader, ledgerwriter, transactionhistory): guava -> 33.7.2-jre, jackson-databind -> 2.22.3.
   - Result: each image down to 2 findings, the accepted Spring CVEs below.

3. Accepted risk: `.trivyignore` (repo root)
   - CVE-2026-47884: Spring RCE via XsltView path limitation
   - CVE-2026-47890: Spring SSE stream corruption with views
   - Affects spring-webmvc 6.2.19. Fix exists only in Spring 7.0.x, which needs a Spring Boot 4 migration.
   - Justification checked: `grep -rniE "XsltView|SseEmitter|text/event-stream" src/ledger` returned nothing.
   - Both entries expire 2027-03-01. After that Trivy stops ignoring them and the CI gate fails, which forces a re-review.
   - Also accepted (from summary): zlib1g HIGH.

4. Java CI workflow
   - Replaced `build-balancereader.yml` with `build-java-services.yml` (git rename).
   - Matrix: balancereader, ledgerwriter, transactionhistory.
   - Steps: setup-java (temurin 17, maven cache) -> checkstyle + unit tests -> Jib build -> Trivy report (HIGH+CRITICAL, informational) -> Trivy gate (fails on fixable CRITICAL) -> GHCR login and push (push events only).
   - Trivy actions are pinned by commit SHA (v0.36.0).
   - First run: all 3 jobs green.

5. Manifests pointed at own GHCR images
   - 7 app images switched to `ghcr.io/shanthipocha/bank-platform/<svc>:<commit-sha>`. Old upstream `@sha256` digests dropped; the SHA tag is the pin.
   - accounts-db and ledger-db still use upstream `us-central1-docker.pkg.dev/bank-of-anthos-ci/...:v0.6.11@sha256:...`.
   - GHCR packages were checked as anonymously pullable (`docker manifest inspect` with an empty DOCKER_CONFIG).
   - Deployed to kind: all 9 pods Running, 0 restarts on app pods. Frontend verified via port-forward on 8081; payments and transfers work.

## 3. Current image pins

| Service | Source | Tag (commit SHA) |
|---|---|---|
| frontend, userservice, contacts, loadgenerator | Python workflow | b35f93ef05bac173213ccd33a0d9324854dccb74 |
| balancereader, ledgerwriter, transactionhistory | Java workflow | 3b4b56fd01424018a92483ec5c612aa9d2b117d8 |
| accounts-db, ledger-db | upstream | v0.6.11 + digest |

## 4. Key commits (main)
- b0cfb11d: guava/jackson pin fixes + `.trivyignore`
- 3b4b56fd: Java matrix workflow
- eddbd58d: manifests point to GHCR images

## 5. Lessons and gotchas
- A BOM property does not override an explicit `<version>` in `<dependencies>`. Check `./mvnw dependency:tree` and grep for hardcoded versions.
- Guava versions need the `-jre` suffix (33.7.2-jre). Dropping it breaks resolution.
- Use grep to get exact line numbers before `sed -i 'NNs/...'`. Off-by-one edits happened once.
- When chaining build and scan, gate the scan on "BUILD SUCCESS" (use `tee` to a log). Otherwise a failed build scans the stale image.
- New GHCR packages are private by default. Make them public or use an imagePullSecret.
- `gh api` for package versions needs the `read:packages` scope (`gh auth refresh -s read:packages`).
- Port 8080 port-forward failed locally (likely port clash). 8081 works.
- Manifests pin to the commit SHA, so every rebuild needs a manifest bump. Dependabot will not do this. Plan: ArgoCD plus an image updater.

## 6. Known issues (open)
1. Plaintext DB passwords in ConfigMaps (move to Secrets, later an external secret manager).
2. Single DB replica, no HA.
3. No DB backups.
4. accounts-db and ledger-db use upstream images, with no CI build or scan.
5. Spring 6.2 CVEs accepted until 2027-03-01, then Boot 4 migration or re-accept.
6. zlib1g HIGH accepted (from summary).
7. Java gate only fails on fixable CRITICAL. HIGH is report-only.

## 7. Next steps
1. (Optional, on kind) ConfigMap -> Secrets for DB passwords.
2. AWS: Terraform for VPC + EKS, then ArgoCD, deploy from this repo.
3. GCP: GKE, same ArgoCD and manifests.
4. Azure: AKS, same pattern.
5. Keep manifests cloud-neutral so GCP and Azure are mostly new Terraform.
6. Later: DB backups, HA, image updater, Boot 4 migration.

## 8. Handy commands
- Cluster: `kubectl config use-context kind-bank`
- Pods: `kubectl get pods`
- Frontend: `kubectl port-forward svc/frontend 8081:80`, then open http://localhost:8081
- Latest Java CI run: `gh run list --workflow=build-java-services.yml --limit 1`
- Image tags in GHCR: `gh api "/user/packages/container/bank-platform%2F<svc>/versions" --jq '.[0].metadata.container.tags[0]'`
