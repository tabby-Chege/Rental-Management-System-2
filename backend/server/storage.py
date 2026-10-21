import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class ObjectStorageError(Exception):
    pass


def _client_and_bucket():
    bucket = current_app.config.get("S3_BUCKET")
    if not bucket:
        raise ObjectStorageError("Private document storage is not configured")

    client = boto3.client(
        "s3",
        endpoint_url=current_app.config.get("S3_ENDPOINT_URL"),
        region_name=current_app.config["S3_REGION"],
    )
    return client, bucket


def put_private_object(key, contents, content_type):
    client, bucket = _client_and_bucket()
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=contents,
            ContentType=content_type,
            ServerSideEncryption=current_app.config[
                "S3_SERVER_SIDE_ENCRYPTION"
            ],
        )
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError("Private document storage upload failed") from error


def get_private_object(key):
    client, bucket = _client_and_bucket()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError, KeyError) as error:
        raise ObjectStorageError("Private document storage download failed") from error


def delete_private_object(key):
    client, bucket = _client_and_bucket()
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError("Private document storage delete failed") from error
