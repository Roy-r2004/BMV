"""Smoke test for BmvLogger and WatchBmv."""
from app.infrastructure.logging import WatchBmv, configure_logging, get_logger


def main() -> None:
    configure_logging("debug")
    log = get_logger("LoggingSmokeTest")
    log.trace("trace message")
    log.debug("debug message")
    log.info("info message")
    log.warning("warning message")
    with WatchBmv("smoke-section", log):
        sum(range(1000))
    print("logging smoke test OK")


if __name__ == "__main__":
    main()
