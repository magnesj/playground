#!/usr/bin/env python3
"""Set the playback sound of every instrument in a MuseScore 4 score to
MuseSounds "Muse Keys -> Grand Piano".

Only audiosettings.json inside the .mscz is changed; the notation (instrument
names, clefs, staff types) stays as it is, exactly like picking the sound in
MuseScore's Mixer.

  * every track except the metronome gets the Grand Piano resource
  * parts (and chord-symbol playback) that have no track yet get one, so
    staves added outside MuseScore also play piano
  * the resource id format follows <programVersion> (4.6+ uses "167",
    older files "Muse Keys\\Grand Piano\\167")

Usage
  python set_piano_sound.py IN.mscz OUT.mscz
"""
import argparse
import copy
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

UID = '167'
ATTRIBUTES = {
    'museCategory': 'Muse Keys',
    'museName': 'Grand Piano',
    'musePack': 'Muse Keys',
    'museUID': UID,
    'museVendorName': 'Muse',
    'playbackSetupData': 'keyboards.piano',
}
DEFAULT_OUT = {
    'auxSends': [{'active': True, 'signalAmount': 0.15000000596046448},
                 {'active': True, 'signalAmount': 0.30000001192092896}],
    'balance': 0,
    'fxChain': {},
    'volumeDb': 0,
}
SOLO_MUTE = {'mute': False, 'solo': False}


def fail(msg):
    sys.exit('ERROR: ' + msg)


def resource(program_version):
    nums = [int(x) for x in re.findall(r'\d+', program_version)[:2]] or [4, 6]
    rid = UID if nums >= [4, 6] else 'Muse Keys\\Grand Piano\\' + UID
    return {'resourceMeta': {'attributes': dict(ATTRIBUTES), 'hasNativeEditorSupport': False,
                             'id': rid, 'type': 'muse_sampler_sound_pack', 'vendor': 'MuseSounds'},
            'unitConfiguration': {}}


def wanted_tracks(score):
    """(partId, instrumentId) pairs MuseScore creates playback tracks for."""
    harmony_staves = {st.get('id') for st in score.findall('Staff') if st.find('.//Harmony') is not None}
    out = []
    for part in score.findall('Part'):
        pid = part.get('id')
        out.append((pid, part.find('Instrument').get('id')))
        if any(st.get('id') in harmony_staves for st in part.findall('Staff')):
            out.append((pid, 'chord_symbols'))
    return out


def apply(mscx_bytes, settings):
    root = ET.fromstring(mscx_bytes)
    score = root.find('Score')
    version = root.findtext('programVersion') or score.findtext('programVersion') or ''
    res = resource(version)
    tracks = settings.setdefault('tracks', [])
    names = {p.get('id'): ' '.join((p.findtext('trackName') or '').split()) or p.get('id')
             for p in score.findall('Part')}

    template_out = next((t['out'] for t in tracks if t.get('instrumentId') != 'metronome' and 'out' in t),
                        DEFAULT_OUT)
    log, existing = [], set()
    for t in tracks:
        if t.get('instrumentId') == 'metronome':
            continue
        key = (t.get('partId'), t.get('instrumentId'))
        existing.add(key)
        old = t.get('in', {}).get('resourceMeta', {})
        was = ' / '.join(filter(None, [old.get('attributes', {}).get('musePack') or old.get('id'),
                                       old.get('attributes', {}).get('museName')])) or 'none'
        t['in'] = copy.deepcopy(res)
        log.append(f'{names.get(key[0], key[0])} [{key[1]}]: {was} -> Muse Keys / Grand Piano')

    for pid, iid in wanted_tracks(score):
        if (pid, iid) in existing:
            continue
        tracks.append({'in': copy.deepcopy(res), 'instrumentId': iid, 'out': copy.deepcopy(template_out),
                       'partId': pid, 'soloMuteState': dict(SOLO_MUTE)})
        log.append(f'{names.get(pid, pid)} [{iid}]: added track with Muse Keys / Grand Piano')
    settings.setdefault('activeSoundProfile', 'MuseSounds')
    return version, log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    a = ap.parse_args()
    if not a.input.lower().endswith('.mscz'):
        fail('input must be a .mscz file (playback sounds live in its audiosettings.json)')

    with zipfile.ZipFile(a.input) as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
    files = {info.filename: data for info, data in entries}
    mscx = next((n for n in files if n.endswith('.mscx') and '/' not in n), None)
    if mscx is None:
        fail('no score .mscx found in the archive')
    settings = json.loads(files['audiosettings.json']) if 'audiosettings.json' in files else {}

    version, log = apply(files[mscx], settings)
    new_json = json.dumps(settings, indent=4).encode('utf-8')

    out_dir = os.path.dirname(os.path.abspath(a.output))
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(a.output, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info, data in entries:
            zout.writestr(info, new_json if info.filename == 'audiosettings.json' else data)
        if 'audiosettings.json' not in files:
            zout.writestr('audiosettings.json', new_json)

    print(f'programVersion {version}')
    print('\n'.join(log) if log else 'No instrument tracks found.')
    print(f'Wrote {a.output}')


if __name__ == '__main__':
    main()
