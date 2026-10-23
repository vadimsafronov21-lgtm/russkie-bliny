"""Build with an isolated DLL search path, avoiding unrelated app runtimes."""
import os
import subprocess
import sys
import argparse
from pathlib import Path

root=Path(__file__).resolve().parent
env=os.environ.copy()
win=Path(env.get('SystemRoot',r'C:\Windows'))
env['PATH']=os.pathsep.join([str(Path(sys.executable).parent),sys.base_prefix,str(win/'System32'),str(win)])
parser=argparse.ArgumentParser(); parser.add_argument('--console',action='store_true'); parser.add_argument('--distpath',default='dist')
options=parser.parse_args()
console='--console' if options.console else '--windowed'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile',console,'--add-data','assets;assets','--distpath',options.distpath,'--name','RusskieBliny','app.py'],cwd=root,env=env,check=True)
