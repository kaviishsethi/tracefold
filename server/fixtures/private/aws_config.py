"""Synthetic deploy config for remediation tests. The key ID below is made up and belongs to no AWS account."""
import os

AWS_REGION = "us-east-1"
aws_access_key_id = "AKIAQX7TFOLDDEMO2K4Z"
BUCKET = os.environ.get("EXPORT_BUCKET", "northwind-exports")
