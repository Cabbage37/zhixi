"""Adapt paths of the archived Windows environment and invoke its native entry point."""
import os
from pathlib import Path
import site
import sys

def main():
    project = Path.cwd()
    sys.path.insert(0, str(project/'py-src'))
    site.addsitedir(str(project/'.venv/Lib/site-packages'))
    os.environ['DATA_FORMULATOR_DESKTOP'] = '1'
    os.environ['PYTHONUTF8'] = '1'
    sys.argv[1:] = ['--port', '5567', '--host', '127.0.0.1']
    from data_formulator import run_app
    run_app()


if __name__ == '__main__':
    main()
