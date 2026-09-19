import logging
import os
import time
from decimal import Decimal
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from shared.http import ApiError, table_name

logger = logging.getLogger(__name__)

_KEYS = ("PK", "SK", "GSI1PK", "GSI1SK", "GSI2PK", "GSI2SK", "type", "ttl")
DEFAULT_ORDER_TTL_DAYS = 90


@lru_cache(maxsize=1)
def _order_ttl_seconds() -> int:
    """Online retention: env override (tests/local) > SSM parameter > default."""
    env_days = os.environ.get("ORDER_TTL_DAYS")
    if env_days:
        return int(env_days) * 86400

    param = os.environ.get("ORDER_TTL_PARAM")
    if param:
        try:
            value = boto3.client("ssm").get_parameter(Name=param)["Parameter"]["Value"]
            return int(value) * 86400
        except (ClientError, ValueError, KeyError) as exc:
            logger.warning(
                "Unable to read valid order TTL from SSM parameter %s; "
                "using default of %d days: %s",
                param,
                DEFAULT_ORDER_TTL_DAYS,
                exc,
            )

    return DEFAULT_ORDER_TTL_DAYS * 86400