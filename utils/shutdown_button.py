from gpiozero import Button
from signal import pause
import subprocess
import logging
import sys
import time

# Register this as a service.  When a button is pressed, pi will do a clean
# shutdown. You can use  sudo journalctl -u shutdown-button.service to viewitems
# its log.


# BCM GPIO 26 = physical pin 37
# The button connects GPIO 26 to GND.
# The internal pull-up keeps GPIO 26 HIGH until the button is pressed.
button = Button(26, pull_up=True)

# Send logging messages to stdout.
# systemd captures stdout and puts it into the journal.
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def shutdown():
    # Log the button press first.
    logger.info("SHUTDOWN BUTTON PRESSED")

    # Make sure the log message is pushed out immediately.
    for handler in logger.handlers:
        handler.flush()

    # Give systemd a moment to record the message before shutting down.
    time.sleep(0.2)

    logger.info("Initiating clean Linux shutdown")

    try:
        # Ask Linux to perform a normal, clean shutdown.
        subprocess.run(
            ["sudo", "shutdown", "-h", "now"],
            capture_output=True,
            text=True
        )

    except Exception:
        # Record any unexpected error in the systemd journal.
        logger.exception("ERROR while attempting shutdown")


# Call shutdown() when the button is pressed.
button.when_pressed = shutdown

logger.info("Shutdown button monitor started")
logger.info("Monitoring BCM GPIO 26 / physical pin 37")

# Keep the program alive waiting for the GPIO interrupt.
pause()
