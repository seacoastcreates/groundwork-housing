#!/usr/bin/env bash
# First-boot setup for the Groundwork server (Ubuntu 24.04, arm64). Run as root by EC2 user data:
#   bootstrap.sh <source-dir> <bundle-dir> <backup-bucket> <region> <artifact-bucket> <sagemaker-role-arn> <train-image-uri>
# Installs PostgreSQL, Python, Node and nginx; restores the database; builds the Next.js site; and runs
# the API and site as systemd services behind nginx on port 80.
set -euxo pipefail
SRC_IN=$1
BUNDLE=$2
BACKUP_BUCKET=$3
REGION=$4
ARTIFACT_BUCKET=$5
SAGEMAKER_ROLE_ARN=$6
TRAIN_IMAGE_URI=$7
APP=/opt/groundwork
SRC=$APP/src
DB=housingtracker
export DEBIAN_FRONTEND=noninteractive

# ---- swap (the Next.js build and the monthly database load need more than 2 GB) ----------------
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---- packages ----------------------------------------------------------------------------------
apt-get update
apt-get install -y postgresql nginx python3.12-venv python3-dev build-essential cmake libgomp1 curl ca-certificates
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# ---- app user and code -------------------------------------------------------------------------
id groundwork >/dev/null 2>&1 || useradd --system --create-home --home-dir "$APP" --shell /usr/sbin/nologin groundwork
rm -rf "$SRC" && mkdir -p "$SRC" && cp -a "$SRC_IN"/. "$SRC"/
mkdir -p "$SRC/data/raw" "$SRC/ml/artifacts"
chown -R groundwork:groundwork "$APP"

# ---- settings shared by the API service and the monthly refresh --------------------------------
mkdir -p /etc/groundwork
cat > /etc/groundwork/groundwork.env <<ENV
AWS_REGION=$REGION
AWS_DEFAULT_REGION=$REGION
DATABASE_URL=postgresql+psycopg:///$DB
BACKUP_BUCKET=$BACKUP_BUCKET
ARTIFACT_BUCKET=$ARTIFACT_BUCKET
SAGEMAKER_ROLE_ARN=$SAGEMAKER_ROLE_ARN
TRAIN_IMAGE_URI=$TRAIN_IMAGE_URI
TRAIN_INSTANCE_TYPE=ml.t3.xlarge
ENV
chmod 640 /etc/groundwork/groundwork.env && chgrp groundwork /etc/groundwork/groundwork.env

# ---- database: restore the newest backup (or the deploy bundle) --------------------------------
# A redeploy after a monthly refresh must not roll the data back, so prefer the latest S3 backup.
DUMP="$BUNDLE/$DB.dump"
# `aws s3 ls` exits non-zero on an empty prefix; with pipefail that would abort setup, so allow it.
LATEST=$( (/usr/local/bin/aws s3 ls "s3://$BACKUP_BUCKET/backups/" 2>/dev/null || true) | sort | tail -n 1 | awk '{print $4}')
if [ -n "$LATEST" ]; then
  /usr/local/bin/aws s3 cp "s3://$BACKUP_BUCKET/backups/$LATEST" /tmp/latest.dump --only-show-errors && DUMP=/tmp/latest.dump
  chmod 644 /tmp/latest.dump
fi
echo "restoring database from $DUMP"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname = 'groundwork'" | grep -q 1 || sudo -u postgres createuser groundwork
sudo -u postgres dropdb --if-exists $DB
sudo -u postgres createdb -O groundwork $DB
sudo -u groundwork pg_restore --no-owner --role=groundwork -d $DB "$DUMP"
# Bring an older backup up to the current schema (every statement is CREATE ... IF NOT EXISTS).
sudo -u groundwork psql -q $DB -f "$SRC/backend/db/schema.sql"

# ---- API (FastAPI) -----------------------------------------------------------------------------
cd "$SRC/backend"
sudo -u groundwork python3.12 -m venv "$SRC/.venv"
sudo -u groundwork "$SRC/.venv/bin/pip" install --quiet --upgrade pip
sudo -u groundwork "$SRC/.venv/bin/pip" install --quiet -r requirements.txt

cat > /etc/systemd/system/groundwork-api.service <<UNIT
[Unit]
Description=Groundwork API
After=network.target postgresql.service
[Service]
User=groundwork
WorkingDirectory=$SRC/backend
EnvironmentFile=/etc/groundwork/groundwork.env
Environment=CORS_ORIGINS=
ExecStart=$SRC/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now groundwork-api
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/api/v1/health && break; sleep 2; done

# ---- website (Next.js) --------------------------------------------------------------------------
# The API must be up during the build: pages without search params are prerendered from it.
cd "$SRC/frontend"
sudo -u groundwork npm ci --no-audit --no-fund
sudo -u groundwork env API_URL=http://127.0.0.1:8000 NODE_OPTIONS=--max-old-space-size=1536 NEXT_TELEMETRY_DISABLED=1 npm run build

cat > /etc/systemd/system/groundwork-web.service <<UNIT
[Unit]
Description=Groundwork website
After=network.target groundwork-api.service
[Service]
User=groundwork
WorkingDirectory=$SRC/frontend
Environment=NODE_ENV=production
Environment=API_URL=http://127.0.0.1:8000
Environment=NEXT_TELEMETRY_DISABLED=1
ExecStart=/usr/bin/npm run start -- -p 3000 -H 127.0.0.1
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now groundwork-web

# ---- nginx: /api/v1/ -> FastAPI (public API docs at /api/v1/docs), everything else -> Next.js ---
cat > /etc/nginx/sites-available/groundwork <<'NGINX'
server {
    listen 80 default_server;
    server_name _;
    client_max_body_size 1m;
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/groundwork /etc/nginx/sites-enabled/groundwork
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ---- weekly database backup to S3 (data changes monthly; kept 30 days by the bucket lifecycle) ----
cat > /etc/cron.d/groundwork-backup <<CRON
AWS_DEFAULT_REGION=$REGION
15 7 * * 0 groundwork pg_dump -Fc $DB | /usr/local/bin/aws s3 cp - s3://$BACKUP_BUCKET/backups/$DB-\$(date +\%F).dump --only-show-errors
CRON

for i in $(seq 1 60); do curl -sf http://127.0.0.1/ >/dev/null && break; sleep 2; done
# Retried like the checks above: right after the nginx reload a single try can fail and, under set -e,
# abort the script just short of the end.
for i in $(seq 1 30); do curl -sf http://127.0.0.1/api/v1/health && break; sleep 2; done
echo "GROUNDWORK BOOTSTRAP COMPLETE"
