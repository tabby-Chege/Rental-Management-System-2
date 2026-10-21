import os
import re
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class ObjectStorageError(Exception):
    pass


def _local_object_path(key):
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
        raise ObjectStorageError("Invalid private object key")
    return Path(current_app.config["LOCAL_STORAGE_PATH"]) / key


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


def _uses_local_storage():
    backend = current_app.config.get("OBJECT_STORAGE_BACKEND", "s3")
    if backend not in {"local", "s3"}:
        raise ObjectStorageError("Object storage backend is not supported")
    return backend == "local"


def put_private_object(key, contents, content_type):
    if _uses_local_storage():
        path = _local_object_path(key)
        temporary_path = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".upload-", delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(contents)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        except OSError as error:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    current_app.logger.exception("Could not remove temporary storage object")
            raise ObjectStorageError("Private document storage upload failed") from error
        return

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
    if _uses_local_storage():
        try:
            return _local_object_path(key).read_bytes()
        except OSError as error:
            raise ObjectStorageError("Private document storage download failed") from error

    client, bucket = _client_and_bucket()
    try:
        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError, KeyError) as error:
        raise ObjectStorageError("Private document storage download failed") from error


def delete_private_object(key):
    if _uses_local_storage():
        try:
            _local_object_path(key).unlink(missing_ok=True)
        except OSError as error:
            raise ObjectStorageError("Private document storage delete failed") from error
        return

    client, bucket = _client_and_bucket()
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as error:
        raise ObjectStorageError("Private document storage delete failed") from error
