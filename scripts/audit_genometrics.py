#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

TAXDUMP_URL="https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
UA="GenomeObservatoryLive/0.1 (public research dashboard; contact via repository)"
VIRIDIPLANTAE=33090

def first(d,*paths,default=None):
    for path in paths:
        x=d
        try:
            for key in path.split("."):
                x=x[int(key)] if isinstance(x,list) else x[key]
            if x not in (None,""): return x
        except (KeyError,IndexError,TypeError,ValueError):
            pass
    return default

def load_parents():
    with tempfile.TemporaryDirectory(prefix="gol_tax_") as td:
        td=Path(td); arc=td/"taxdump.tar.gz"
        req=Request(TAXDUMP_URL,headers={"User-Agent":UA})
        with urlopen(req,timeout=120) as src, arc.open("wb") as dst: shutil.copyfileobj(src,dst)
        with tarfile.open(arc,"r:gz") as tf:
            m=next(m for m in tf.getmembers() if Path(m.name).name=="nodes.dmp")
            tf.extract(m,td)
        node=next(td.rglob("nodes.dmp"))
        parent={}
        with node.open(errors="replace") as fh:
            for line in fh:
                p=line.split("|")
                if len(p)>=2: parent[int(p[0].strip())]=int(p[1].strip())
        return parent

def is_desc(tid,ancestor,parent,cache):
    key=(tid,ancestor)
    if key in cache:return cache[key]
    cur=tid; seen=set()
    while cur and cur not in seen:
        if cur==ancestor:
            cache[key]=True; return True
        seen.add(cur)
        nxt=parent.get(cur)
        if nxt is None or nxt==cur:break
        cur=nxt
    cache[key]=False; return False

def stream(cmd):
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    assert p.stdout is not None
    for line in p.stdout:
        line=line.strip()
        if line: yield json.loads(line)
    err=p.stderr.read() if p.stderr else ""
    code=p.wait()
    if code: raise RuntimeError(f"datasets failed {code}: {err[-4000:]}")

def main():
    parent=load_parents(); cache={}
    assm_cmd=["datasets","summary","genome","taxon","Eukaryota","--assembly-source","GenBank","--assembly-level","chromosome,complete","--as-json-lines"]
    n=0; mito=0; plant=0; plant_plastid=0
    desc=Counter(); pdesc=Counter()
    for r in stream(assm_cmd):
        n+=1
        tid=first(r,"organism.tax_id","organism.taxId","tax_id","organism.taxid")
        try: tid=int(tid)
        except: tid=None
        organelles=first(r,"organelle_info","organelleInfo",default=[]) or []
        ds=[]
        for o in organelles:
            d=str(first(o,"description",default="") or "").strip()
            if d:
                desc[d]+=1; ds.append(d.casefold())
        if any("mitochond" in d for d in ds): mito+=1
        if tid and is_desc(tid,VIRIDIPLANTAE,parent,cache):
            plant+=1
            for o in organelles:
                d=str(first(o,"description",default="") or "").strip()
                if d:pdesc[d]+=1
            if any(("chloroplast" in d or "plastid" in d) for d in ds): plant_plastid+=1

    seq_cmd=["datasets","summary","genome","taxon","Eukaryota","--assembly-source","GenBank","--assembly-level","chromosome,complete","--report","sequence","--as-json-lines"]
    label=Counter(); loc=Counter(); role=Counter(); candidate=Counter(); by_assm={}
    pat=re.compile(r"(?i)(^|[^a-z])(x|y|z|w|u|v)([0-9a-z._-]*)([^a-z]|$)|sex|gonosom")
    rows=0
    for r in stream(seq_cmd):
        rows+=1
        a=str(first(r,"assembly_accession","assemblyAccession","accession",default="") or "")
        c=str(first(r,"chr_name","chrName",default="") or "").strip()
        l=str(first(r,"assigned_molecule_location_type","assignedMoleculeLocationType",default="") or "").strip()
        ro=str(first(r,"role",default="") or "").strip()
        if l:loc[l]+=1
        if ro:role[ro]+=1
        if c:
            label[c]+=1
            if pat.search(c): candidate[c]+=1
        if a and c and (ro.casefold()=="assembled-molecule" or l.casefold()=="chromosome"):
            by_assm.setdefault(a,set()).add(c)

    print("ASSEMBLIES",n)
    print("MITO_ASSOC",mito,mito/n if n else 0)
    print("VIRIDIPLANTAE",plant)
    print("VIRIDIPLANTAE_PLASTID",plant_plastid,plant_plastid/plant if plant else 0)
    print("ORGANELLE_DESCRIPTIONS")
    for k,v in desc.most_common(80): print(v,"\t",k)
    print("PLANT_ORGANELLE_DESCRIPTIONS")
    for k,v in pdesc.most_common(80): print(v,"\t",k)
    print("SEQUENCE_ROWS",rows)
    print("ASSEMBLIES_WITH_CHROM_LABELS",len(by_assm))
    print("LOCATION_TYPES")
    for k,v in loc.most_common(): print(v,"\t",k)
    print("ROLES")
    for k,v in role.most_common(): print(v,"\t",k)
    print("SEX_CANDIDATE_LABELS")
    for k,v in candidate.most_common(400): print(v,"\t",k)
    print("TOP_CHR_LABELS")
    for k,v in label.most_common(250): print(v,"\t",k)

if __name__=="__main__":
    main()
