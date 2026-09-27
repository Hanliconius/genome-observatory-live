#!/usr/bin/env python3
"""One-time bootstrap: fetch all GenBank eukaryote chromosome/complete assembly metadata,
collapse it immediately to daily counts + first-seen species, and discard raw historical rows.
Run before update.py on first deployment. This intentionally stores no sequence data."""
import json, subprocess
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data'/'dashboard.json'
cmd=['datasets','summary','genome','taxon','Eukaryota','--assembly-source','GenBank','--assembly-level','chromosome,complete','--as-json-lines']
p=subprocess.Popen(cmd,stdout=subprocess.PIPE,text=True)
daily=defaultdict(lambda:{'assemblies':0,'species':set(),'first_time_species':0}); first={}
for line in p.stdout:
    try:r=json.loads(line); info=r.get('assembly_info') or {};org=r.get('organism') or {};d=str(info.get('release_date',''))[:10];name=org.get('organism_name')
    except Exception:continue
    if not d or not name:continue
    daily[d]['assemblies']+=1;daily[d]['species'].add(name)
    if name not in first or d<first[name]:first[name]=d
p.wait()
if p.returncode:raise SystemExit(p.returncode)
for name,d in first.items():daily[d]['first_time_species']+=1
rows=[{'date':d,'assemblies':v['assemblies'],'species':len(v['species']),'first_time_species':v['first_time_species']} for d,v in sorted(daily.items())]
old=json.loads(OUT.read_text()) if OUT.exists() else {}
old['daily']=rows;old['species_first_seen']=first;old.pop('demo_seed',None);OUT.write_text(json.dumps(old,indent=2)+'\n')
print(f'bootstrapped {sum(x["assemblies"] for x in rows)} assemblies across {len(rows)} release dates; raw records discarded')
