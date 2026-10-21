"""Build with an isolated DLL search path, avoiding unrelated app runtimes."""
import os
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parent
env=os.environ.copy()
win=Path(env.get('SystemRoot',r'C:\Windows'))
env['PATH']=os.pathsep.join([str(Path(sys.executable).parent),sys.base_prefix,str(win/'System32'),str(win)])
console='--console' if '--console' in sys.argv else '--windowed'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile',console,'--add-data','assets;assets','--name','RusskieBliny','app.py'],cwd=root,env=env,check=True)
