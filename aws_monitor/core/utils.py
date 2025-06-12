"""Utility functions and decorators for AWS Cost & Usage Monitor."""

import time
import functools
import logging
from typing import Callable, Any, TypeVar, Optional, Tuple, Type, Union
from datetime import datetime, timedelta
import random
from botocore.exceptions import ClientError, BotoCoreError, NoCredentialsError

logger = logging.getLogger(__name__)

# Type variable for generic functions
F = TypeVar("F", bound=Callable[..., Any])


def exponential_backoff_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (ClientError, BotoCoreError),
) -> Callable[[F], F]:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter to delays
        exceptions: Tuple of exceptions to catch and retry

    Returns:
        Decorated function
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    # Check if it's a throttling error
                    if isinstance(e, ClientError):
                        error_code = e.response.get("Error", {}).get("Code", "")
                        if error_code in ["ThrottlingException", "TooManyRequestsException"]:
                            logger.warning(f"Throttled on attempt {attempt + 1}/{max_retries + 1}")
                        elif error_code in ["AccessDenied", "UnauthorizedOperation"]:
                            # Don't retry on permission errors
                            logger.error(f"Permission error: {e}")
                            raise

                    if attempt < max_retries:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (exponential_base**attempt), max_delay)

                        # Add jitter if enabled
                        if jitter:
                            delay *= 0.5 + random.random()

                        logger.info(
                            f"Retrying {func.__name__} after {delay:.2f}s "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries reached for {func.__name__}. "
                            f"Last error: {last_exception}"
                        )

            # If we get here, we've exhausted all retries
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def rate_limit(calls: int, period: float) -> Callable[[F], F]:
    """
    Decorator to rate limit function calls.

    Args:
        calls: Number of calls allowed
        period: Time period in seconds

    Returns:
        Decorated function
    """
    min_interval = period / calls
    last_called = [0.0]

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret

        return wrapper

    return decorator


def handle_aws_errors(func: F) -> F:
    """
    Decorator to handle common AWS errors gracefully.

    Args:
        func: Function to decorate

    Returns:
        Decorated function
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NoCredentialsError:
            logger.error(
                "No AWS credentials found. Please configure your credentials "
                "using AWS CLI, environment variables, or IAM role."
            )
            raise
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = e.response.get("Error", {}).get("Message", "")

            if error_code == "ExpiredToken":
                logger.error("AWS credentials have expired. Please refresh your credentials.")
            elif error_code == "AccessDenied":
                logger.error(f"Access denied: {error_message}")
            elif error_code == "ServiceUnavailable":
                logger.error("AWS service is temporarily unavailable. Please try again later.")
            else:
                logger.error(f"AWS API error ({error_code}): {error_message}")

            raise
        except BotoCoreError as e:
            logger.error(f"AWS connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise

    return wrapper


def validate_date_range(start_date: datetime, end_date: datetime) -> bool:
    """
    Validate date range for AWS APIs.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        True if valid

    Raises:
        ValueError: If date range is invalid
    """
    if start_date >= end_date:
        raise ValueError("Start date must be before end date")

    # AWS Cost Explorer has a limit of 1 year
    if (end_date - start_date).days > 365:
        raise ValueError("Date range cannot exceed 365 days for Cost Explorer API")

    # Can't query future dates
    if end_date > datetime.now():
        raise ValueError("End date cannot be in the future")

    return True


def format_bytes(bytes_value: Union[int, float]) -> str:
    """
    Format bytes into human-readable string.

    Args:
        bytes_value: Number of bytes

    Returns:
        Formatted string
    """
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(bytes_value) < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} EB"


def format_duration(seconds: Union[int, float]) -> str:
    """
    Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    elif seconds < 86400:
        hours = seconds / 3600
        return f"{hours:.1f}h"
    else:
        days = seconds / 86400
        return f"{days:.1f}d"


def chunked(iterable, size: int):
    """
    Split an iterable into chunks of specified size.

    Args:
        iterable: Iterable to chunk
        size: Chunk size

    Yields:
        Chunks of the iterable
    """
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk


def safe_get(data: dict, path: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary value using dot notation.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., 'foo.bar.baz')
        default: Default value if path not found

    Returns:
        Value at path or default
    """
    keys = path.split(".")
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
            if data is None:
                return default
        else:
            return default
    return data


def parse_arn(arn: str) -> Dict[str, Optional[str]]:
    """
    Parse an AWS ARN into its components.

    Args:
        arn: AWS ARN string

    Returns:
        Dictionary with ARN components
    """
    # ARN format: arn:partition:service:region:account-id:resource
    parts = arn.split(":", 5)

    if len(parts) < 6 or parts[0] != "arn":
        raise ValueError(f"Invalid ARN format: {arn}")

    resource_parts = parts[5].split("/", 1)

    return {
        "arn": arn,
        "partition": parts[1],
        "service": parts[2],
        "region": parts[3],
        "account_id": parts[4],
        "resource_type": resource_parts[0],
        "resource_id": resource_parts[1] if len(resource_parts) > 1 else None,
    }


def calculate_time_range(
    hours: Optional[int] = None,
    days: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """
    Calculate time range based on various inputs.

    Args:
        hours: Number of hours to look back
        days: Number of days to look back
        start_date: Explicit start date
        end_date: Explicit end date

    Returns:
        Tuple of (start_date, end_date)
    """
    if start_date and end_date:
        return start_date, end_date

    if not end_date:
        end_date = datetime.now()

    if hours:
        start_date = end_date - timedelta(hours=hours)
    elif days:
        start_date = end_date - timedelta(days=days)
    elif not start_date:
        # Default to last 24 hours
        start_date = end_date - timedelta(hours=24)

    return start_date, end_date


import itertools  # noqa: E402


class CachedProperty:
    """
    Decorator for creating cached properties.

    The property is calculated on first access and then cached.
    """

    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        value = self.func(obj)
        obj.__dict__[self.func.__name__] = value
        return value


def singleton(cls):
    """
    Decorator to make a class a singleton.

    Args:
        cls: Class to make singleton

    Returns:
        Singleton class
    """
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance
