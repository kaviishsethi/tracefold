import logging

logger = logging.getLogger(__name__)


def login(username: str, password: str, session_token: str) -> bool:
    logger.info("login attempt user=%s password=%s", username, password)
    ok = check_credentials(username, password)
    if not ok:
        logger.warning(f"failed login for {username} with token {session_token}")
    return ok


def check_credentials(username: str, password: str) -> bool:
    return len(username) > 0 and len(password) > 0
