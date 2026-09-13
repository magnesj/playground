#!/usr/bin/env python3
"""Export one MP3 rehearsal track per choir voice from a MuseScore 4 score.

For every soprano / alto / tenor / bass part (found by part name), a temporary
copy of the score is made where that part's mixer volume is set to the maximum
(+12 dB), and MuseScore exports the full song from it to "<score> - <part>.mp3".

  * other tracks keep their volume unless --others-db is given; +12 dB on
    one voice can clip, --master-db -6 (or --others-db) avoids that
  * solo is cleared on every track and the featured voice is unmuted, so each
    export contains the whole song
  * the original score is never modified

Usage
  python export_voice_mp3.py SCORE.mscz [--out-dir DIR] [--others-db DB]
                             [--master-db DB] [--parts "S,A,T,B"]
                             [--bitrate KBPS] [--list]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

MAX_DB = 12  # top of the MuseScore 4 mixer volume slider
VOICES = {
    'soprano': r's|sop|sopr|sopran|soprano|sopranos|soprani',
    'alto': r'a|alt|alto|altos|alti|contralto',
    'tenor': r't|ten|tenor|tenors|tenorer|tenori',
    'bass': r'b|bas|bass|basses|bassi|basser',
}
MUSESCORE_CANDIDATES = [
    r'C:\Program Files\MuseScore 4\bin\MuseScore4.exe',
    '/Applications/MuseScore 4.app/Contents/MacOS/mscore',
]


def fail(msg):
    sys.exit('ERROR: ' + msg)


def clean(text):
    return ' '.join((text or '').split())


def text_of(el):
    """Element text with <br/> as a space ('T<br/>B' -> 'T B')."""
    if el is None:
        return ''
    parts = [el.text or '']
    for c in el.iter():
        if c is not el:
            parts += [' ' if c.tag == 'br' else (c.text or ''), c.tail or '']
    return clean(''.join(parts))


def part_name(part):
    """Staff long name, track name or short name - the first that names a voice, else the first set.
    Either field can be stale or a bare number, so none of them is trusted alone."""
    inst = part.find('Instrument')
    names = [n for n in (text_of(inst.find('longName')), text_of(part.find('trackName')),
                         text_of(inst.find('shortName'))) if n not in ('', '|')]
    return next((n for n in names if voices_in(n)), names[0] if names else 'Part ' + part.get('id'))


def unique_names(parts):
    """Number repeated names ('Tenor', 'Tenor' -> 'Tenor 1', 'Tenor 2') so files don't collide."""
    total = {}
    for _, n in parts:
        total[n.lower()] = total.get(n.lower(), 0) + 1
    seen, out = {}, []
    for pid, n in parts:
        if total[n.lower()] > 1:
            seen[n.lower()] = seen.get(n.lower(), 0) + 1
            n = f'{n} {seen[n.lower()]}'
        out.append((pid, n))
    return out


def voices_in(name):
    """Voice categories named in a part name, e.g. 'Sopran 2' -> {'soprano'}."""
    words = re.split(r'[\s/&+,.\-]+|(?<=\D)(?=\d)', name.lower())
    return {v for v, pat in VOICES.items() for w in words if re.fullmatch(r'(%s)\d*' % pat, w)}


def find_musescore(explicit):
    for c in [explicit, os.environ.get('MUSESCORE')] + MUSESCORE_CANDIDATES + \
             [shutil.which(n) for n in ('MuseScore4', 'mscore4portable', 'mscore')]:
        if c and os.path.isfile(c):
            return c
    fail('MuseScore 4 not found; pass --musescore PATH')


def safe_filename(name):
    return re.sub(r'[<>:"/\\|?*]+', '-', name).strip(' .') or 'part'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('score')
    ap.add_argument('--out-dir', help='folder for the MP3s (default: next to the score)')
    ap.add_argument('--others-db', type=float,
                    help='set every other track (incl. piano) to this volume in dB, e.g. -12 '
                         '(default: leave unchanged)')
    ap.add_argument('--master-db', type=float,
                    help='set the master volume in dB, e.g. -6, to avoid clipping (default: unchanged)')
    ap.add_argument('--parts', help='comma-separated part names to export instead of auto-detection')
    ap.add_argument('--bitrate', type=int, help='MP3 bitrate in kbps (default: MuseScore setting)')
    ap.add_argument('--musescore', help='path to MuseScore4.exe')
    ap.add_argument('--list', action='store_true', help='list the parts and exit')
    a = ap.parse_args()

    if not a.score.lower().endswith('.mscz'):
        fail('score must be a .mscz file (mixer volumes live in its audiosettings.json)')
    # read everything once: Dropbox/OneDrive can rewrite the file while we work
    with zipfile.ZipFile(a.score) as z:
        entries = [(info, z.read(info.filename)) for info in z.infolist()]
    files = {info.filename: data for info, data in entries}
    mscx = next((n for n in files if n.endswith('.mscx') and '/' not in n), None)
    if mscx is None:
        fail('no score .mscx found in the archive')
    if 'audiosettings.json' not in files:
        fail('no audiosettings.json in the score; open and save it once in MuseScore 4')
    settings = json.loads(files['audiosettings.json'])
    score = ET.fromstring(files[mscx]).find('Score')
    parts = unique_names([(p.get('id'), part_name(p)) for p in score.findall('Part')])

    if a.list:
        for pid, name in parts:
            print(f'part {pid}: {name}  voices={sorted(voices_in(name)) or "-"}')
        return

    if a.parts:
        wanted = [clean(n) for n in a.parts.split(',') if clean(n)]
        by_name = {name.lower(): (pid, name) for pid, name in parts}
        missing = [n for n in wanted if n.lower() not in by_name]
        if missing:
            fail(f'unknown part(s) {missing}; parts are {[n for _, n in parts]}')
        selected = [by_name[n.lower()] for n in wanted]
    else:
        selected = [(pid, name) for pid, name in parts if voices_in(name)]
        if not selected:
            fail(f'no soprano/alto/tenor/bass parts found in {[n for _, n in parts]}; use --parts')

    names = dict(parts)
    track_parts = {t.get('partId') for t in settings.get('tracks', [])}
    ms = find_musescore(a.musescore)
    stem = os.path.splitext(os.path.basename(a.score))[0]
    out_dir = os.path.abspath(a.out_dir or os.path.dirname(os.path.abspath(a.score)))
    os.makedirs(out_dir, exist_ok=True)

    for pid, name in selected:
        if len(voices_in(name)) > 1:
            print(f'NOTE: "{name}" holds several voices; they are exported together '
                  f'(split the staff first to get one track per voice)')
        if pid not in track_parts:
            print(f'WARNING: "{name}" has no mixer track; skipped (open and save the score in MuseScore)')
            continue
        s = json.loads(json.dumps(settings))
        if a.master_db is not None:
            s.setdefault('master', {})['volumeDb'] = a.master_db
        muted = []
        for t in s['tracks']:
            if t.get('instrumentId') == 'metronome':
                continue
            out = t.setdefault('out', {})
            state = t.setdefault('soloMuteState', {'mute': False, 'solo': False})
            state['solo'] = False
            if t.get('partId') == pid:
                out['volumeDb'] = MAX_DB
                state['mute'] = False
            else:
                if a.others_db is not None:
                    out['volumeDb'] = a.others_db
                if state.get('mute'):
                    muted.append(names.get(t.get('partId'), t.get('partId')))
        data = json.dumps(s, indent=4).encode('utf-8')

        mp3 = os.path.join(out_dir, f'{stem} - {safe_filename(name)}.mp3')
        with tempfile.TemporaryDirectory() as tmp:
            tmp_score = os.path.join(tmp, f'{stem} - {safe_filename(name)}.mscz')
            with zipfile.ZipFile(tmp_score, 'w', zipfile.ZIP_DEFLATED) as zout:
                for info, blob in entries:
                    zout.writestr(info, data if info.filename == 'audiosettings.json' else blob)
            cmd = [ms, '-o', mp3, tmp_score] + (['-b', str(a.bitrate)] if a.bitrate else [])
            if os.path.exists(mp3):
                os.remove(mp3)
            r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
        if not os.path.isfile(mp3) or os.path.getsize(mp3) == 0:
            fail(f'MuseScore did not write {mp3} (exit {r.returncode})\n{r.stderr[-2000:]}')
        extra = f'; kept muted: {", ".join(dict.fromkeys(muted))}' if muted else ''
        print(f'{name}: +{MAX_DB} dB -> {mp3} ({os.path.getsize(mp3) // 1024} KB){extra}')


if __name__ == '__main__':
    main()
