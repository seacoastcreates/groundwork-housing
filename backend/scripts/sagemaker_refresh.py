"""Run the monthly SageMaker refresh job and bring its results back to this server.

    python -m scripts.sagemaker_refresh

1. Start a SageMaker Processing job on the training image (ml/sagemaker_job.py): it downloads every
   source, builds the panels, backtests and trains.
2. Wait for it, then download its raw files into data/raw and its model into ml/artifacts/<version>,
   and copy the model into the S3 registry.
3. Print the model version; deploy/refresh-aws.sh then loads the database and publishes the model.

Configuration comes from the environment: ARTIFACT_BUCKET, SAGEMAKER_ROLE_ARN, TRAIN_IMAGE_URI and
optionally TRAIN_INSTANCE_TYPE (default ml.t3.xlarge).
"""
import os
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, WaiterError

from homeprice.data import RAW
from ingest.publish import ARTIFACTS

OUTPUT_DIR = "/opt/ml/processing/output"


def download_prefix(s3, bucket: str, prefix: str, local: Path) -> int:
    local.mkdir(parents=True, exist_ok=True)
    n = 0
    for key in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix + "/").search("Contents[].Key"):
        if key and not key.endswith("/"):
            s3.download_file(bucket, key, str(local / Path(key).name))
            n += 1
    return n


def run(bucket: str, role_arn: str, image_uri: str, instance_type: str) -> str:
    sm, s3 = boto3.client("sagemaker"), boto3.client("s3")
    job = time.strftime("groundwork-refresh-%Y%m%d-%H%M%S", time.gmtime())
    run_prefix = f"runs/{job}"
    sm.create_processing_job(
        ProcessingJobName=job,
        RoleArn=role_arn,
        AppSpecification={"ImageUri": image_uri},
        ProcessingResources={"ClusterConfig": {"InstanceCount": 1, "InstanceType": instance_type, "VolumeSizeInGB": 30}},
        ProcessingOutputConfig={"Outputs": [{
            "OutputName": "results",
            "S3Output": {"S3Uri": f"s3://{bucket}/{run_prefix}/output", "LocalPath": OUTPUT_DIR,
                         "S3UploadMode": "EndOfJob"},
        }]},
        # The job resolves the FRED API key from this secret at runtime (only its name is passed here).
        Environment={"FRED_SECRET_ID": os.environ.get("FRED_SECRET_ID", "groundwork/fred"),
                     "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")},
        StoppingCondition={"MaxRuntimeInSeconds": 3 * 3600},
        Tags=[{"Key": "project", "Value": "groundwork"}],
    )
    print(f"Started SageMaker Processing job {job} on {instance_type}", flush=True)
    try:
        sm.get_waiter("processing_job_completed_or_stopped").wait(
            ProcessingJobName=job, WaiterConfig={"Delay": 60, "MaxAttempts": 180})
    except WaiterError:
        pass  # the status check below reports the failure reason
    desc = sm.describe_processing_job(ProcessingJobName=job)
    if desc["ProcessingJobStatus"] != "Completed":
        raise RuntimeError(f"{job} ended {desc['ProcessingJobStatus']}: {desc.get('FailureReason', 'no reason given')}")
    minutes = (desc["ProcessingEndTime"] - desc["ProcessingStartTime"]).total_seconds() / 60
    print(f"{job} completed in {minutes:.0f} min", flush=True)

    n_raw = download_prefix(s3, bucket, f"{run_prefix}/output/raw", RAW)
    version = s3.get_object(Bucket=bucket, Key=f"{run_prefix}/output/model/VERSION")["Body"].read().decode().strip()
    n_model = download_prefix(s3, bucket, f"{run_prefix}/output/model", ARTIFACTS / version)
    for f in (ARTIFACTS / version).iterdir():
        s3.upload_file(str(f), bucket, f"registry/{version}/{f.name}")
    print(f"downloaded {n_raw} raw files and {n_model} model files for {version}", flush=True)
    return version


def main() -> int:
    try:
        version = run(os.environ["ARTIFACT_BUCKET"], os.environ["SAGEMAKER_ROLE_ARN"], os.environ["TRAIN_IMAGE_URI"],
                      os.environ.get("TRAIN_INSTANCE_TYPE", "ml.t3.xlarge"))
        print(f"MODEL_VERSION={version}")
        return 0
    except (ClientError, RuntimeError, KeyError) as e:
        print(f"Refresh job failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
