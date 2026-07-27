#!/usr/bin/env python3
"""Baut BWL-Trainer.html aus app_template.html + fragen_single.json (+ fragen_multi.json)."""
import json, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
def p(n): return os.path.join(BASE, n)

fragen = []
with open(p('fragen_single.json'), encoding='utf-8') as fh:
    fragen += json.load(fh)
for extra in ('fragen_multi.json', 'fragen_schwer.json'):
    if os.path.exists(p(extra)):
        with open(p(extra), encoding='utf-8') as fh:
            fragen += json.load(fh)

# Themennamen für die Anzeige glätten
UMLAUT = {
    'Businessplan und Gruendung': 'Businessplan und Gründung',
    'Kalkulation und Liquiditaet': 'Kalkulation und Liquidität',
}
for q in fragen:
    q['thema'] = UMLAUT.get(q['thema'], q['thema'])

# Identische Fragetexte gehoeren zu einer Familie, auch wenn Antwortsets und
# Schwierigkeit variieren. So erscheint dieselbe Frage nie doppelt in einer Runde.
textgruppen = {}
for q in fragen:
    key = re.sub(r'\s+', ' ', q['frage']).strip().casefold()
    textgruppen.setdefault(key, []).append(q)
duplikatgruppen = 0
for nr, gruppe in enumerate((g for g in textgruppen.values() if len(g) > 1), 1):
    familie = next((q.get('familie') for q in gruppe if q.get('familie')), None)
    familie = familie or 'gleicher-fragetext-%02d' % nr
    for q in gruppe:
        q['familie'] = familie
    duplikatgruppen += 1

# IDs neu und stabil vergeben, Struktur prüfen
fehler = []
for i, q in enumerate(fragen, 1):
    q['id'] = 'q%03d' % i
    opts = q['optionen']
    if len(opts) != len(set(opts)):
        fehler.append((q['id'], 'doppelte Antwortoption'))
    if not (4 <= len(opts) <= 10):
        fehler.append((q['id'], '%d Antwortoptionen (erlaubt 4-10)' % len(opts)))
    if isinstance(q['richtig'], list):
        if not (2 <= len(q['richtig']) <= 5):
            fehler.append((q['id'], 'Mehrfachfrage mit %d richtigen' % len(q['richtig'])))
        if len(q['richtig']) >= len(opts):
            fehler.append((q['id'], 'alle Optionen als richtig markiert'))
        if any(not (0 <= r < len(opts)) for r in q['richtig']):
            fehler.append((q['id'], 'Index ausserhalb der Optionen'))
        if len(set(q['richtig'])) != len(q['richtig']):
            fehler.append((q['id'], 'doppelter Index'))
    else:
        if not (0 <= q['richtig'] < len(opts)):
            fehler.append((q['id'], 'Index ausserhalb der Optionen'))
    if q['schwierigkeit'] not in ('leicht', 'mittel', 'schwer'):
        fehler.append((q['id'], 'unbekannte Schwierigkeit'))
    if 'essential' in q and q['essential'] is not True:
        fehler.append((q['id'], 'essential muss true sein oder fehlen'))
    for feld in ('frage', 'erklaerung', 'thema'):
        if not str(q.get(feld, '')).strip():
            fehler.append((q['id'], 'leeres Feld: ' + feld))

# Fachhinweise bleiben getrennt vom Vorlesungsinhalt. So kann die App die
# Prüfungsantwort zeigen und fachliche Abweichungen sichtbar kennzeichnen.
hinweis_file = p('fachhinweise.json')
if os.path.exists(hinweis_file):
    with open(hinweis_file, encoding='utf-8') as fh:
        hinweis_gruppen = json.load(fh)
    fragen_nach_id = {q['id']: q for q in fragen}
    verwendete_ids = set()
    for gruppe in hinweis_gruppen:
        ids = gruppe.get('ids', [])
        hinweis = {
            k: gruppe[k] for k in ('hinweis', 'quelle', 'url')
            if str(gruppe.get(k, '')).strip()
        }
        if not ids:
            fehler.append(('Fachhinweis', 'Gruppe ohne IDs'))
        if not hinweis.get('hinweis'):
            fehler.append((', '.join(ids) or 'Fachhinweis', 'Hinweistext fehlt'))
        for qid in ids:
            if qid in verwendete_ids:
                fehler.append((qid, 'mehrfacher Fachhinweis'))
            elif qid not in fragen_nach_id:
                fehler.append((qid, 'Fachhinweis verweist auf unbekannte Frage'))
            else:
                fragen_nach_id[qid]['fachhinweis'] = dict(hinweis)
                verwendete_ids.add(qid)

if fehler:
    print('ABBRUCH — Strukturfehler:', file=sys.stderr)
    for f in fehler:
        print('  ', f[0], f[1], file=sys.stderr)
    sys.exit(1)

daten = json.dumps(fragen, ensure_ascii=False, separators=(',', ':'))
# </script> im Inhalt würde den JSON-Block vorzeitig schliessen
daten = daten.replace('</', '<\\/')

with open(p('app_template.html'), encoding='utf-8') as fh:
    tpl = fh.read()
for ph in ('__FRAGEN__', '__STILE__'):
    if ph not in tpl:
        print('ABBRUCH — Platzhalter %s fehlt in app_template.html' % ph, file=sys.stderr)
        sys.exit(1)

# Ein einziges Designsystem verhindert visuelle Abweichungen zwischen Ansichten.
style_file = p('editorial.css')
if not os.path.exists(style_file):
    print('ABBRUCH — editorial.css fehlt', file=sys.stderr)
    sys.exit(1)
with open(style_file, encoding='utf-8') as fh:
    stil_css = fh.read().strip()
if '@import' in stil_css or 'url(' in stil_css:
    print('ABBRUCH — editorial.css enthaelt @import oder url()', file=sys.stderr)
    sys.exit(1)
if '[data-style="editorial"]' not in stil_css:
    print('ABBRUCH — editorial.css ist nicht auf editorial gescopt', file=sys.stderr)
    sys.exit(1)

seite = tpl.replace('__FRAGEN__', daten).replace('__STILE__', stil_css)
for ausgabe in ('BWL-Trainer.html', 'index.html'):
    with open(p(ausgabe), 'w', encoding='utf-8') as fh:
        fh.write(seite)

from collections import Counter
einfach = sum(1 for q in fragen if not isinstance(q['richtig'], list))
mehrfach = len(fragen) - einfach
familien = sum(1 for q in fragen if q.get('familie'))
essential = sum(1 for q in fragen if q.get('essential'))
fachhinweise = sum(1 for q in fragen if q.get('fachhinweis'))
print('BWL-Trainer.html und index.html gebaut')
print('  Fragen gesamt : %d  (%d einfach, %d mehrfach)' % (len(fragen), einfach, mehrfach))
print('  mit Familie   : %d' % familien)
print('  Text-Duplikate: %d Gruppen zusammengefuehrt' % duplikatgruppen)
print('  Optionen      :', dict(sorted(Counter(len(q['optionen']) for q in fragen).items())))
print('  Schwierigkeit :', dict(Counter(q['schwierigkeit'] for q in fragen)))
print('  Essential     : %d' % essential)
print('  Fachhinweise  : %d' % fachhinweise)
print('  Themen        : %d' % len(set(q['thema'] for q in fragen)))
print('  Designsysteme : 1  (editorial)')
print('  Stil-CSS      : %.0f KB' % (len(stil_css) / 1024))
print('  Dateigroesse  : %.0f KB' % (os.path.getsize(p('index.html')) / 1024))
