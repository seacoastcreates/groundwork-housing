# SageMaker Processing image for the monthly refresh (built by CDK from the repo root). Library versions
# come from pyproject.toml's exact pins, which the API server also installs.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# LightGBM needs the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/program
COPY ml/pyproject.toml ml/pyproject.toml
COPY ml/homeprice ml/homeprice
RUN pip install --no-cache-dir ./ml boto3
COPY backend/ingest backend/ingest
COPY ml/train.py ml/sagemaker_job.py ml/
COPY ml/reports/*.json ml/reports/
ENTRYPOINT ["python3", "/opt/program/ml/sagemaker_job.py"]
