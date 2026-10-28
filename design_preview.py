"""Start the review build with a persistent, separate synthetic database."""
import os
from pathlib import Path
import sys

from app import main


if __name__=='__main__':
    sys.argv.append('--design-preview')
    if '--data-dir' not in sys.argv:
        directory=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'RusskieBliny-DesignPreview'
        sys.argv.extend(['--data-dir',str(directory)])
    main()
