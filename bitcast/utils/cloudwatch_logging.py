import os
import logging


def get_cloudwatch_handler(log_group: str, stream_name: str) -> logging.Handler | None:
    """
    Returns a configured CloudWatch log handler, or None if CloudWatch is disabled
    or unavailable.

    Controlled by the ENABLE_CLOUDWATCH env var. Authenticates via the EC2 IAM role
    (no credentials needed in code). AWS_REGION defaults to us-east-1.
    """
    if os.environ.get("ENABLE_CLOUDWATCH", "").lower() != "true":
        return None

    try:
        import boto3
        import watchtower

        handler = watchtower.CloudWatchLogHandler(
            log_group_name=log_group,
            log_stream_name=stream_name,
            boto3_session=boto3.Session(
                region_name=os.environ.get("AWS_REGION", "us-east-1")
            ),
            create_log_group=True,
            create_log_stream=True,
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        return handler

    except Exception as e:
        logging.warning(f"CloudWatch logging not available: {e}")
        return None
