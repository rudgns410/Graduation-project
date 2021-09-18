import glob
import os
import shutil
import subprocess
from pathlib import Path


vid_formats = ['.mov', '.avi', '.mp4', '']

def add_audio(source, out):
    # Add audio from source videos to output files
    print(source, out)
    temp_folder = "temp"
    if os.path.exists(temp_folder):
        shutil.rmtree(temp_folder)
    os.makedirs(temp_folder)

    path = str(Path(source))
    files = []
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, '*.*')))
    elif os.path.isfile(path):
        files = [path]

    videos = [x for x in files if os.path.splitext(x)[-1].lower() in vid_formats]

    for source_path in videos:
        save_path = str(Path(out) / Path(source_path).name)
        if not os.path.isfile(save_path):
            continue
        temp_path = str(Path(temp_folder) / Path(source_path).name)
        os.rename(save_path, temp_path)

        p = subprocess.Popen(['ffmpeg', '-y', '-i', source_path, '-i', temp_path, '-c:v', 'libx264', '-c:a', 'copy', '-map', '1:v:0', '-map', '0:a:0', save_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p_out, err = p.communicate()
        exitcode = p.returncode
        if exitcode != 0:
            print(exitcode, p_out.decode('utf8'), err.decode('utf8'))

    shutil.rmtree(temp_folder)