import logging

log = logging.getLogger("billing")


def summarize(token_count: int, password_policy: str, api_key: str) -> None:
    log.info("processed %d tokens under policy %s", token_count, password_policy)
    log.debug("api key fingerprint %s", redact(api_key))
    print("password reset emails are sent from the support address")


def redact(value: str) -> str:
    return value[:2] + "…"
