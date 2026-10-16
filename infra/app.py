#!/usr/bin/env python3
import os

import aws_cdk as cdk

from groundwork_stack import GroundworkStack

app = cdk.App()
GroundworkStack(
    app, "Groundwork",
    env=cdk.Environment(account="699191579533", region="us-east-1"),
    # Budget alerts go here; kept out of the (public) repo: pass -c alert_email=... or set ALERT_EMAIL.
    alert_email=app.node.try_get_context("alert_email") or os.environ["ALERT_EMAIL"],
    # AWS-managed prefix list of CloudFront's origin-facing IPs in us-east-1.
    cloudfront_prefix_list=app.node.try_get_context("cloudfront_prefix_list") or "pl-3b927c52",
    domain_name=app.node.try_get_context("domain_name") or "groundwork.36dunes.com",
    description="Groundwork - US home values and forecasts (EC2 + CloudFront + SageMaker refresh)",
)
app.synth()
