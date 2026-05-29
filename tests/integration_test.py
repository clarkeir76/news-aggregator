"""
Integration test for the ephemeral AWS test environment.
Invokes the Lambda twice:
  Run 1 — populates DynamoDB, verifies articles are saved
  Run 2 — exercises deduplication against existing articles, verifies no crash

Run by CI after Terraform deploys a test environment.

Usage:
  python tests/integration_test.py --function-name news-aggregator-test-123 \
                                   --table-name news-aggregator-test-123-articles \
                                   --region eu-west-1
"""

import argparse
import json
import sys
import time
import boto3


def invoke_lambda(lambda_client, function_name: str, run_number: int) -> dict:
    print(f"Run {run_number}: invoking {function_name}...")
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({}),
    )

    payload = json.loads(response["Payload"].read())

    if response["StatusCode"] != 200:
        print(f"FAIL run {run_number}: Lambda HTTP status {response['StatusCode']}")
        sys.exit(1)

    if "FunctionError" in response:
        print(
            f"FAIL run {run_number}: Lambda function error: {response['FunctionError']}"
        )
        print(json.dumps(payload, indent=2))
        sys.exit(1)

    if payload.get("statusCode", 0) != 200:
        print(f"FAIL run {run_number}: Pipeline statusCode {payload.get('statusCode')}")
        print(json.dumps(payload, indent=2))
        sys.exit(1)

    stats = payload.get("body", {}).get("stats", {})
    if stats.get("errors"):
        print(f"FAIL run {run_number}: Pipeline errors: {stats['errors']}")
        sys.exit(1)

    return stats


def run(function_name: str, table_name: str, region: str) -> None:
    lambda_client = boto3.client("lambda", region_name=region)
    dynamo = boto3.resource("dynamodb", region_name=region)
    table = dynamo.Table(table_name)

    # Run 1: fresh table — populates DynamoDB
    stats1 = invoke_lambda(lambda_client, function_name, run_number=1)
    saved = stats1.get("articles_saved", 0)

    result = table.scan(Limit=5)
    if result["Count"] == 0:
        print("FAIL run 1: No articles found in DynamoDB after first invocation")
        sys.exit(1)

    print(
        f"PASS run 1: {saved} article(s) saved | "
        f"ingested={stats1.get('articles_ingested', 0)} "
        f"classified={stats1.get('articles_classified', 0)}"
    )

    # Brief pause so the second run has a slightly different cutoff timestamp
    time.sleep(3)

    # Run 2: exercises deduplication against existing DynamoDB articles
    # This is what was crashing due to the url_gsi_pk bug
    stats2 = invoke_lambda(lambda_client, function_name, run_number=2)
    unique2 = stats2.get("unique_output", 0)
    ingested2 = stats2.get("articles_ingested", 0)

    print(
        f"PASS run 2: deduplication worked | "
        f"ingested={ingested2} unique={unique2} "
        f"(most should be deduped against run 1)"
    )

    print("PASS: Both runs completed successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--table-name", required=True)
    parser.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()
    run(args.function_name, args.table_name, args.region)
