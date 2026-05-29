"""
Integration test for the ephemeral AWS test environment.
Invokes the Lambda, waits for completion, then verifies DynamoDB has articles.
Run by CI after Terraform deploys a test environment.

Usage:
  python tests/integration_test.py --function-name news-aggregator-test-123 \
                                   --table-name news-aggregator-test-123-articles \
                                   --region eu-west-1
"""

import argparse
import json
import sys
import boto3


def run(function_name: str, table_name: str, region: str) -> None:
    lambda_client = boto3.client("lambda", region_name=region)
    dynamo = boto3.resource("dynamodb", region_name=region)

    print(f"Invoking Lambda: {function_name}")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({}),
    )

    payload = json.loads(response["Payload"].read())
    print(f"Lambda response status: {response['StatusCode']}")

    if response["StatusCode"] != 200:
        print(f"FAIL: Lambda HTTP status {response['StatusCode']}")
        sys.exit(1)

    if "FunctionError" in response:
        print(f"FAIL: Lambda function error: {response['FunctionError']}")
        print(json.dumps(payload, indent=2))
        sys.exit(1)

    status_code = payload.get("statusCode", 0)
    if status_code != 200:
        print(f"FAIL: Pipeline returned statusCode {status_code}")
        print(json.dumps(payload, indent=2))
        sys.exit(1)

    stats = payload.get("body", {}).get("stats", {})
    errors = stats.get("errors", [])
    if errors:
        print(f"FAIL: Pipeline reported errors: {errors}")
        sys.exit(1)

    # Verify articles were saved to DynamoDB
    table = dynamo.Table(table_name)
    result = table.scan(Limit=5)
    article_count = result["Count"]

    if article_count == 0:
        print("FAIL: No articles found in DynamoDB after Lambda run")
        sys.exit(1)

    ingested = stats.get("articles_ingested", 0)
    classified = stats.get("articles_classified", 0)
    saved = stats.get("articles_saved", 0)

    print(
        f"PASS: {article_count} article(s) in DynamoDB | "
        f"ingested={ingested} classified={classified} saved={saved}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()
    run(args.function_name, args.table_name, args.region)
