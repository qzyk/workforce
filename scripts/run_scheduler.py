"""
Proces dedicat APScheduler (Faza 3).

Ruleaza scheduler-ul intr-un SINGUR loc, ca containerele web sa poata avea
WORKERS>1 fara job-uri duplicate (web-ul porneste cu RUN_SCHEDULER=0).

Folosit ca `entrypoint` al serviciului `scheduler` din docker-compose.
"""

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Asiguram ca scheduler-ul chiar porneste in acest proces
os.environ['RUN_SCHEDULER'] = '1'


def main():
    from app import create_app
    # create_app() apeleaza init_scheduler() (RUN_SCHEDULER=1) -> scheduler activ
    create_app('default')
    print('[scheduler] pornit. Astept job-uri (Ctrl-C pentru oprire)...', flush=True)
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        print('[scheduler] oprit.', flush=True)


if __name__ == '__main__':
    main()
