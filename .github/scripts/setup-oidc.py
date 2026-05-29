"""Setup script for GitHub OIDC authentication with AWS"""

import json
import subprocess
import sys

ACCOUNT_ID = input("Enter your AWS Account ID: ").strip()
GITHUB_ORG = input("Enter your GitHub organization: ").strip()
REPO_NAME = input("Enter your repository name: ").strip()

# 1. Create OIDC provider
print("\n[1/3] Creating OpenID Connect provider...")
try:
    subprocess.run(
        [
            "aws", "iam", "create-open-id-connect-provider",
            "--url", "https://token.actions.githubusercontent.com",
            "--client-id-list", "sts.amazonaws.com",
            "--thumbprint-list", "6938fd4d98bab03faadb97b34396831e3780aea1"
        ],
        check=True,
        capture_output=True
    )
    print("✓ OIDC provider created")
except subprocess.CalledProcessError as e:
    if "EntityAlreadyExists" in e.stderr.decode():
        print("✓ OIDC provider already exists")
    else:
        print(f"✗ Error: {e.stderr.decode()}")
        sys.exit(1)

# 2. Create IAM role
print("\n[2/3] Creating IAM role...")
trust_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": f"arn:aws:iam::{ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": f"repo:{GITHUB_ORG}/{REPO_NAME}:*"
                }
            }
        }
    ]
}

try:
    subprocess.run(
        [
            "aws", "iam", "create-role",
            "--role-name", "news-aggregator-github-actions",
            "--assume-role-policy-document", json.dumps(trust_policy)
        ],
        check=True,
        capture_output=True
    )
    print("✓ IAM role created")
except subprocess.CalledProcessError as e:
    if "EntityAlreadyExists" in e.stderr.decode():
        print("✓ IAM role already exists")
    else:
        print(f"✗ Error: {e.stderr.decode()}")
        sys.exit(1)

# 3. Attach policy
print("\n[3/3] Attaching policy...")
try:
    subprocess.run(
        [
            "aws", "iam", "attach-role-policy",
            "--role-name", "news-aggregator-github-actions",
            "--policy-arn", "arn:aws:iam::aws:policy/AdministratorAccess"
        ],
        check=True,
        capture_output=True
    )
    print("✓ Policy attached")
except subprocess.CalledProcessError as e:
    print(f"✗ Error: {e.stderr.decode()}")
    sys.exit(1)

# Print final instructions
print("\n" + "="*60)
print("✓ GitHub OIDC Setup Complete!")
print("="*60)
print(f"\nAdd the following GitHub Secrets:")
print(f"\nAWS_ROLE_ARN: arn:aws:iam::{ACCOUNT_ID}:role/news-aggregator-github-actions")
print("\nOther secrets to add:")
print("- OPENAI_API_KEY")
print("- SLACK_WEBHOOK_TECH")
print("- SLACK_WEBHOOK_AI")
print("- SLACK_WEBHOOK_EDUCATION")
print("- SLACK_WEBHOOK_CYBER_SECURITY")
