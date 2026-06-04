"""
Retry with exponential backoff for HTTP calls.
Handles transient server errors without blowing the turn timeout.
"""
import time
import requests


def with_retry(fn, max_attempts: int = 3, base_delay: float = 0.1, budget: float = 4.0):
    """
    Call fn() with exponential backoff.
    Gives up if total elapsed time would exceed budget.

    Args:
        fn: callable with no args (use lambda or functools.partial)
        max_attempts: max number of tries
        base_delay: initial wait between retries (doubles each time)
        budget: hard time ceiling — won't retry if we're close to it
    """
    t_start = time.perf_counter()
    last_exc = None
    delay = base_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except requests.exceptions.Timeout as e:
            last_exc = e
            # Timeout means we're already close to budget — don't retry
            raise RuntimeError(f"HTTP timeout on attempt {attempt} — not retrying") from e
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code < 500:
                raise  # 4xx = our bug, don't retry
            last_exc = e
        except requests.exceptions.RequestException as e:
            last_exc = e

        if attempt == max_attempts:
            break

        elapsed = time.perf_counter() - t_start
        if elapsed + delay > budget * 0.9:
            break  # not enough budget left for another attempt

        time.sleep(delay)
        delay = min(delay * 2, 1.0)  # cap at 1s

    raise RuntimeError(f"Failed after {max_attempts} attempts") from last_exc
