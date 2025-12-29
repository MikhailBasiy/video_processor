from os import getenv

import boto3
from dotenv import load_dotenv

load_dotenv()


def get_s3_client():
    client = boto3.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        aws_access_key_id=getenv("ACCESS_KEY_ID"),
        aws_secret_access_key=getenv("SECRET_ACCESS_KEY"),
    )
    return client


client = get_s3_client()
