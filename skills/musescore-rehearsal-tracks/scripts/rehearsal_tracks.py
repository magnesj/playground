#!/usr/bin/env python3
"""Make choir rehearsal tracks from a MuseScore 4 score in one go:

  1. split shared vocal staves ("S/A", "T B", ...)   musescore-split-voices
  2. set every track to Muse Keys -> Grand Piano      musescore-piano-sound
  3. export one MP3 per voice, that voice at max      musescore-voice-mp3

Shared staves are found by name: a single-staff part whose name holds two
voices (e.g. "Soprano/Alto", "T<br/>B"). The name's words become the new
staff names, highest voice on the upper staff. Override with --split.

Everything is written to OUT-DIR (default "<score folder>/<score> rehearsal"):
the processed score "<score>.mscz" and "<score> - <voice>.mp3" per voice.
The original score is never modified.

Usage
  python rehearsal_tracks.py SCORE.mscz [--out-dir DIR] [--dry-run]
         [--split N:UPPER:LOWER ...] [--no-split] [--divisi upper|lower]
         [--master-db DB] [--others-db DB] [--bitrate KBPS]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPLIT = os.path.join(SKILLS, 'musescore-split-voices', 'scripts', 'split_staff.py')
PIANO = os.path.join(SKILLS, 'musescore-piano-sound', 'scripts', 'set_piano_sound.py')
MP3 = os.path.join(SKILLS, 'musescore-voice-mp3', 'scripts', 'export_voice_mp3.py')
sys.path.insert(0, os.path.dirname(MP3))
from export_voice_mp3 import VOICES, part_name, voices_in  # noqa: E402

RANK = list(VOICES)  # soprano, alto, tenor, bass: high to low


def fail(msg):
    sys.exit('ERROR: ' + msg)


def voice_of(word):
    return next((v for v, pat in VOICES.items() if re.fullmatch(r'(%s)\d*' % pat, word.lower())), None)


def shared_staves(mscz):
    """[(staff_no, part name, upper name, lower name)] for single-staff parts naming two voices."""
    with zipfile.ZipFile(mscz) as z:
        mscx = next(n for n in z.namelist() if n.endswith('.mscx') and '/' not in n)
        score = ET.fromstring(z.read(mscx)).find('Score')
    out, staff_no = [], 0
    for part in score.findall('Part'):
        n = len(part.findall('Staff'))
        staff_no += n
        name = part_name(part)
        if n != 1 or len(voices_in(name)) != 2:
            continue
        words = [w for w in re.split(r'[\s/&+,.\-]+', name) if voice_of(w)]
        words = sorted(dict.fromkeys(words), key=lambda w: RANK.index(voice_of(w)))
        if len(words) == 2:
            out.append((staff_no, name, words[0], words[1]))
    return out


def run(step, cmd):
    print(f'\n== {step}')
    r = subprocess.run([sys.executable] + cmd)
    if r.returncode != 0:
        fail(f'{step} failed (exit {r.returncode}); nothing further was done')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('--out-dir', help='output folder (default: "<score folder>/<score> rehearsal")')
    ap.add_argument('--split', action='append', default=[], metavar='N:UPPER:LOWER',
                    help='split staff N into UPPER/LOWER instead of auto-detection (repeatable)')
    ap.add_argument('--no-split', action='store_true', help='skip the split step')
    ap.add_argument('--divisi', choices=['upper', 'lower'], default='upper')
    ap.add_argument('--master-db', type=float, default=-6, help='master volume for the MP3s (default -6)')
    ap.add_argument('--others-db', type=float)
    ap.add_argument('--bitrate', type=int)
    ap.add_argument('--dry-run', action='store_true', help='show the plan and exit')
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child scripts'

    for s in (SPLIT, PIANO, MP3):
        if not os.path.isfile(s):
            fail(f'missing {s}; the sibling skills must be installed next to this one')
    if not a.score.lower().endswith('.mscz'):
        fail('score must be a .mscz file')
    score = os.path.abspath(a.score)
    stem = os.path.splitext(os.path.basename(score))[0]
    out_dir = os.path.abspath(a.out_dir or os.path.join(os.path.dirname(score), f'{stem} rehearsal'))
    if os.path.normcase(out_dir) == os.path.normcase(os.path.dirname(score)):
        fail('--out-dir must differ from the score folder (the processed score keeps the same name)')

    # read once into a private copy: synced folders (Dropbox) can rewrite the file mid-run
    with tempfile.TemporaryDirectory() as tmp:
        current = os.path.join(tmp, 'input.mscz')
        with open(score, 'rb') as f:
            data = f.read()
        with open(current, 'wb') as f:
            f.write(data)

        if a.no_split:
            splits = []
        elif a.split:
            splits = []
            for s in a.split:
                m = re.fullmatch(r'(\d+):([^:]+):([^:]+)', s)
                if not m:
                    fail(f'--split "{s}" must look like 3:Tenor:Bass')
                splits.append((int(m.group(1)), f'staff {m.group(1)}', m.group(2), m.group(3)))
        else:
            splits = shared_staves(current)

        print('Plan')
        for no, name, up, low in splits:
            print(f'  split staff {no} "{name}" -> "{up}" + "{low}"')
        if not splits:
            print('  no shared vocal staves to split')
        print('  set all tracks to Muse Keys / Grand Piano')
        print(f'  export one MP3 per voice (master {a.master_db:+g} dB'
              + (f', others {a.others_db:+g} dB' if a.others_db is not None else '') + ')')
        print(f'  output: {out_dir}')
        if a.dry_run:
            return

        # bottom staff first so earlier staff numbers stay valid
        for i, (no, name, up, low) in enumerate(sorted(splits, reverse=True)):
            nxt = os.path.join(tmp, f'split{i}.mscz')
            run(f'Split staff {no} "{name}"', [SPLIT, current, nxt, '--staff', str(no),
                                               '--upper-name', up, '--lower-name', low,
                                               '--divisi', a.divisi])
            current = nxt

        os.makedirs(out_dir, exist_ok=True)
        final = os.path.join(out_dir, f'{stem}.mscz')
        run('Piano sound', [PIANO, current, final])

        cmd = [MP3, final, '--out-dir', out_dir, '--master-db', str(a.master_db)]
        if a.others_db is not None:
            cmd += ['--others-db', str(a.others_db)]
        if a.bitrate:
            cmd += ['--bitrate', str(a.bitrate)]
        run('Voice MP3s', cmd)
        shutil.rmtree(os.path.join(os.path.dirname(MP3), '__pycache__'), ignore_errors=True)

    print(f'\nDone: {out_dir}')


if __name__ == '__main__':
    main()
