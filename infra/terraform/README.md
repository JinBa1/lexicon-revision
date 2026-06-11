# Ingestion worker infrastructure

Terraform for the queue-backed ingestion service: the Fly-hosted API enqueues
per-paper ingest jobs; an ECS Fargate worker consumes them, converts the PDF
with MinerU (CPU), embeds via Voyage, and indexes into Neon Postgres.

```
            POST /admin/ingest (operator-only)
                        |
   +--------------------v---------------------+
   |  API service (FastAPI, Fly.io)           |
   |  validates + enqueues IngestJobMessage   |
   +--------------------+---------------------+
                        |
                  AWS SQS queue  --redrive(3)-->  DLQ --> CloudWatch alarm
                        |
   +--------------------v---------------------+
   |  Ingestion worker (ECS Fargate, 0<->1    |
   |  via step scaling on queue depth)        |
   |  R2 PDF -> MinerU(CPU) -> chunk ->       |
   |  Voyage embed -> upsert Neon ->          |
   |  media refs to R2                        |
   +-------------------------------------------+

Shared stores: Neon Postgres (+pgvector), Cloudflare R2 (S3-compatible).
```

## What this provisions

- **SQS** standard queue + dead-letter queue (`maxReceiveCount=3` redrive,
  45-minute visibility timeout sized to CPU conversion).
- **ECR** repository for the worker image (multi-GB; lifecycle keeps last 5).
- **ECS Fargate** cluster, task definition (2 vCPU / 8 GB), service with
  desired count owned by autoscaling.
- **Scale-to-zero step scaling**: queue depth ≥ 1 → 1 task; queued +
  in-flight = 0 for 10 consecutive minutes → 0 tasks. Idle cost ≈ $0.
- **IAM**: worker task role (SQS consume only), execution role (ECR pull,
  logs, scoped SSM reads), a `SendMessage`-only IAM user for the Fly API
  producer, and a GitHub OIDC role restricted to `main` for CI image pushes.
- **SSM Parameter Store** SecureStrings for worker secrets (database URL,
  Voyage key, R2 keys).
- **CloudWatch**: worker log group (30-day retention), alarms on DLQ depth,
  oldest-message age, queue-driven scaling.

Fly (API), Neon (Postgres), Cloudflare R2 (object storage), and Clerk (auth)
are deliberately outside Terraform — they pre-date this stack and enter as
variables.

## Decision notes (ADR-style)

**SQS over Redis+ARQ and Kafka.** The stack already runs Redis, so ARQ was
the low-effort option, but SQS gives broker-managed redrive/DLQ semantics and
visibility-timeout redelivery that we'd otherwise hand-roll, and the worker
runs on AWS anyway. Kafka was rejected outright: one producer, one consumer,
low volume — unjustifiable operational weight.

**Per-paper jobs.** One PDF per message makes the idempotency unit, the retry
unit, and the DLQ unit the same thing. Indexing is an upsert, so duplicate
delivery converges instead of corrupting.

**Scale-to-zero step scaling, not always-on.** Ingestion is bursty batch
work nobody waits on interactively. Two step-scaling policies driven by
CloudWatch alarms cost nothing and avoid Lambda glue. The scale-down alarm
uses metric math (`visible + in-flight`) so a long-running conversion —
message invisible while processed — keeps the worker alive.

**No visibility heartbeat (yet).** The worker does not call
`extend_visibility`; the 45-minute timeout must cover the worst-case job. If
a job ever exceeds it, the message redelivers and the idempotent upsert
converges — wasteful but correct. Heartbeating is the planned follow-up if
real papers approach the window.

**Neon and R2 stay put.** Moving Postgres to RDS or objects to S3 would add
cost and a migration for zero product benefit. Cross-cloud is deliberate;
the worker sits in eu-west-2 because Neon does.

**`latest` deploy tag, SHA rollback.** CI pushes both `:latest` and a
commit-SHA tag. The task definition pins `var.worker_image_tag` (default
`latest`) — single-operator convenience; pin a SHA via
`terraform apply -var worker_image_tag=<sha>` to roll back.

## Applying

```bash
cd infra/terraform
AWS_PROFILE=<admin-profile> terraform init
AWS_PROFILE=<admin-profile> terraform plan -out=tf.plan
AWS_PROFILE=<admin-profile> terraform apply tf.plan
```

`terraform.tfvars` (gitignored) supplies: `github_repository`,
`database_url`, `voyage_api_key`, `object_storage_bucket`,
`object_storage_endpoint_url`, `object_storage_access_key_id`,
`object_storage_secret_access_key`.

State is local and gitignored — it contains secret material (SSM values, the
producer access key). Do not commit or share it.

Deployment prerequisites beyond Terraform:
- The worker image must exist in ECR (CI pushes on main; first push is
  manual — see the runbook in the repo's dev docs).
- The Fly API needs `INGEST_QUEUE_PROVIDER=sqs`, `INGEST_QUEUE_URL`,
  `AWS_REGION` (fly.toml) and secrets `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` (producer IAM user) / `ADMIN_EMAILS`.
- A collection's configured `community_id` row must already exist in
  Postgres; the worker never creates communities.

## Cost expectations

| Component | Idle | Active |
|---|---|---|
| SQS | $0 (free tier: 1M req/mo) | ~$0 |
| ECS Fargate (2 vCPU / 8 GB, eu-west-2) | $0 (scaled to zero) | ≈ $0.11/task-hour |
| ECR storage (≈0.8 GB compressed × ≤5 images) | < $1/mo | — |
| CloudWatch logs + alarms | < $1/mo at this volume | — |

## Verified behavior (2026-06-11)

- Fargate task boots from a cold account, resolves SSM secrets, starts
  polling: `{"message": "ingestion worker started", "queue_provider": "sqs"}`.
- Poison message: scale-up alarm fired, worker scaled 0→1 unattended, three
  receives each rejected by schema validation and left undeleted, SQS redrive
  moved the message to the DLQ, DLQ alarm fired. Evidence in the dev docs.
