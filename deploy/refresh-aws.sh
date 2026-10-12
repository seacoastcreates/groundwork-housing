#!/usr/bin/env bash
# Monthly refresh on the server, started by an EventBridge Scheduler -> SSM Run Command schedule (or by
# hand: sudo /opt/groundwork/src/deploy/refresh-aws.sh). SageMaker downloads every source and retrains;
# this server then reloads the database from the job's raw files, publishes the new model, clears the
# site's data cache, and takes a fresh backup.
set -euo pipefail
set -a; . /etc/groundwork/groundwork.env; set +a
SRC=/opt/groundwork/src
cd $SRC/backend
as_app() { sudo -u groundwork --preserve-env=AWS_REGION,AWS_DEFAULT_REGION,ARTIFACT_BUCKET,SAGEMAKER_ROLE_ARN,TRAIN_IMAGE_URI,TRAIN_INSTANCE_TYPE,DATABASE_URL "$@"; }
PY=$SRC/.venv/bin/python
echo "== $(date -u +%FT%TZ) refresh started"
VERSION=$(as_app $PY -m scripts.sagemaker_refresh | tee /dev/stderr | sed -n 's/^MODEL_VERSION=//p')
[ -n "$VERSION" ] || { echo "no model version returned"; exit 1; }
as_app $PY -W ignore -m ingest.load
as_app $PY -m ingest.publish "$VERSION"
# Pages cache API responses for an hour; drop the cache so the new month shows immediately.
rm -rf $SRC/frontend/.next/cache/fetch-cache && systemctl restart groundwork-web
sudo -u groundwork pg_dump -Fc housingtracker | /usr/local/bin/aws s3 cp - "s3://$BACKUP_BUCKET/backups/housingtracker-$(date +%F)-refresh.dump" --only-show-errors
# Keep the server's disk small: raw files live in S3 with the job output.
rm -f $SRC/data/raw/*
echo "== $(date -u +%FT%TZ) refresh complete: $VERSION"
