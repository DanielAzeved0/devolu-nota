import time

from apscheduler.schedulers.background import BackgroundScheduler


def heartbeat() -> None:
    return None


def main() -> None:
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(heartbeat, "interval", minutes=5, id="scheduler_heartbeat")
    scheduler.start()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()

