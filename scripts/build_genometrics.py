#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tarfile
import zipfile
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"genometrics.json"
CACHE=ROOT/"cache"/"sex_chromosome_labels.json"
TAXDUMP_URL="https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"
UA="GenomeObservatoryLive/0.2 (public research dashboard; contact via repository)"
VIRIDIPLANTAE=33090
BATCH_SIZE=250
SEX_CHROMOSOME_QUERY=["X","Y","Z","W","X1","X2","Y1","Y2","Z1","Z2","W1","W2"]

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

def stream(cmd):
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    assert p.stdout is not None
    for line in p.stdout:
        line=line.strip()
        if line: yield json.loads(line)
    err=p.stderr.read() if p.stderr else ""
    code=p.wait()
    if code: raise RuntimeError(f"datasets failed {code}: {err[-4000:]}")

def load_parents():
    with tempfile.TemporaryDirectory(prefix="gol_tax_") as td:
        td=Path(td); arc=td/"taxdump.tar.gz"
        req=Request(TAXDUMP_URL,headers={"User-Agent":UA})
        with urlopen(req,timeout=120) as src, arc.open("wb") as dst:
            shutil.copyfileobj(src,dst)
        with tarfile.open(arc,"r:gz") as tf:
            member=next(m for m in tf.getmembers() if Path(m.name).name=="nodes.dmp")
            tf.extract(member,td)
        node=next(td.rglob("nodes.dmp"))
        parent={}
        with node.open(errors="replace") as fh:
            for line in fh:
                p=line.split("|")
                if len(p)>=2:
                    parent[int(p[0].strip())]=int(p[1].strip())
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

def load_json(path,default):
    try:return json.loads(path.read_text()) if path.exists() else default
    except Exception:return default

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,separators=(",",":"),ensure_ascii=False)+"\n")

def normalize_chr_label(value):
    s=re.sub(r"\s+"," ",str(value or "").strip())
    return s

def sex_token(label):
    """Return X/Y/Z/W only for an explicit sex-style chromosome token."""
    raw=normalize_chr_label(label)
    if not raw:return None
    s=raw.upper().strip()

    patterns=[
        r"^(?:CHR(?:OMOSOME)?[ _.-]*)?([XYZW])(?:[ _.-]*[0-9]+)?$",
        r"^(?:LG|LINKAGE[ _.-]*GROUP)[ _.-]*([XYZW])(?:[ _.-]*[0-9]+)?$",
    ]
    for pat in patterns:
        m=re.match(pat,s)
        if m:return m.group(1)

    if re.search(r"SEX|GONOSOM",s):
        m=re.search(r"(?:^|[^A-Z])([XYZW])(?:[^A-Z]|$)",s)
        if m:return m.group(1)
    return None

def classify_tokens(tokens):
    t=set(tokens)
    if {"X","Y"}<=t and not ({"Z","W"} & t):
        return "XY labelled"
    if {"Z","W"}<=t and not ({"X","Y"} & t):
        return "ZW labelled"
    if t:
        return "Other / partial label"
    return "No X/Y/Z/W label"

def resolve_sex_batch(batch):
    labels=defaultdict(set)
    tokens=defaultdict(set)
    with tempfile.NamedTemporaryFile("w",delete=False,prefix="gol_acc_",suffix=".txt") as fh:
        for a in batch:fh.write(a+"\n")
        path=fh.name
    try:
        cmd=[
            "datasets","summary","genome","accession","--inputfile",path,
            "--report","sequence","--as-json-lines"
        ]
        for r in stream(cmd):
            a=str(first(r,"assembly_accession","assemblyAccession","accession",default="") or "")
            role=str(first(r,"role",default="") or "").casefold()
            loc=str(first(r,"assigned_molecule_location_type","assignedMoleculeLocationType",default="") or "").casefold()
            if not a or not (role=="assembled-molecule" or loc=="chromosome"):
                continue
            c=normalize_chr_label(first(r,"chr_name","chrName",default=""))
            if not c:continue
            labels[a].add(c)
            tok=sex_token(c)
            if tok:tokens[a].add(tok)
    finally:
        Path(path).unlink(missing_ok=True)

    out={}
    for a in batch:
        toks=sorted(tokens.get(a,set()))
        out[a]={
            "category":classify_tokens(toks),
            "tokens":toks,
            "candidate_labels":sorted(x for x in labels.get(a,set()) if sex_token(x)),
        }
    return out


def bulk_bootstrap_sex_cache(accessions):
    """Efficient first fill: download only X/Y/Z/W-style sequence reports."""
    wanted=set(accessions)
    labels=defaultdict(set)
    tokens=defaultdict(set)
    with tempfile.TemporaryDirectory(prefix="gol_sex_bootstrap_") as td:
        zpath=Path(td)/"sex_reports.zip"
        cmd=[
            "datasets","download","genome","taxon","Eukaryota",
            "--assembly-source","GenBank",
            "--assembly-level","chromosome,complete",
            "--chromosomes",",".join(SEX_CHROMOSOME_QUERY),
            "--include","seq-report",
            "--filename",str(zpath),
            "--no-progressbar",
            "--fast-zip-validation",
        ]
        p=subprocess.run(cmd,text=True,capture_output=True)
        if p.returncode:
            raise RuntimeError(f"datasets sex-report download failed {p.returncode}: {p.stderr[-4000:]}")
        with zipfile.ZipFile(zpath) as zf:
            report_names=[n for n in zf.namelist() if n.endswith("/sequence_report.jsonl")]
            print(f"sex labels: bulk package contains {len(report_names)} sequence reports")
            for name in report_names:
                with zf.open(name) as fh:
                    for raw in fh:
                        try:r=json.loads(raw)
                        except Exception:continue
                        a=str(first(r,"assembly_accession","assemblyAccession","accession",default="") or "")
                        if not a or a not in wanted:continue
                        role=str(first(r,"role",default="") or "").casefold()
                        loc=str(first(r,"assigned_molecule_location_type","assignedMoleculeLocationType",default="") or "").casefold()
                        if not (role=="assembled-molecule" or loc=="chromosome"):continue
                        c=normalize_chr_label(first(r,"chr_name","chrName",default=""))
                        if not c:continue
                        tok=sex_token(c)
                        if tok:
                            labels[a].add(c)
                            tokens[a].add(tok)

    out={}
    for a in accessions:
        toks=sorted(tokens.get(a,set()))
        out[a]={
            "category":classify_tokens(toks),
            "tokens":toks,
            "candidate_labels":sorted(labels.get(a,set())),
        }
    return out


def build_sex_cache(accessions,cache):
    missing=[a for a in accessions if a not in cache]
    if not missing:return cache
    if len(missing)>5000:
        print(f"sex labels: bulk-bootstrapping {len(missing)} assemblies")
        cache.update(bulk_bootstrap_sex_cache(accessions))
        write_json(CACHE,cache)
        return cache
    batches=[missing[i:i+BATCH_SIZE] for i in range(0,len(missing),BATCH_SIZE)]
    print(f"sex labels: resolving {len(missing)} uncached assemblies in {len(batches)} incremental batches")
    completed=0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futures={ex.submit(resolve_sex_batch,b):b for b in batches}
        for fut in as_completed(futures):
            cache.update(fut.result())
            completed+=1
            if completed%5==0 or completed==len(batches):
                print(f"sex labels: completed {completed}/{len(batches)} batches")
                write_json(CACHE,cache)
    return cache


def main():
    parent=load_parents(); lineage_cache={}
    cmd=[
        "datasets","summary","genome","taxon","Eukaryota",
        "--assembly-source","GenBank","--assembly-level","chromosome,complete",
        "--as-json-lines"
    ]
    records=[]
    mito=0; plants=0; plastid=0
    organelle_desc=Counter()

    for r in stream(cmd):
        acc=str(first(r,"accession","assembly.accession","assembly_info.assembly_accession",default="") or "")
        if not acc:continue
        taxid=first(r,"organism.tax_id","organism.taxId","tax_id","organism.taxid")
        try: taxid=int(taxid)
        except (TypeError,ValueError): taxid=None

        organelles=first(r,"organelle_info","organelleInfo",default=[]) or []
        descriptions=[]
        for o in organelles:
            d=str(first(o,"description",default="") or "").strip()
            if d:
                descriptions.append(d.casefold())
                organelle_desc[d]+=1

        has_mito=any("mitochond" in d for d in descriptions)
        if has_mito:mito+=1

        is_plant=bool(taxid and is_desc(taxid,VIRIDIPLANTAE,parent,lineage_cache))
        has_plastid=any(("chloroplast" in d or "plastid" in d) for d in descriptions)
        if is_plant:
            plants+=1
            if has_plastid:plastid+=1

        records.append({"accession":acc,"taxid":taxid})

    accessions=[x["accession"] for x in records]
    sex_cache=load_json(CACHE,{})
    sex_cache=build_sex_cache(accessions,sex_cache)

    sex_counts=Counter()
    token_counts=Counter()
    label_counts=Counter()
    for a in accessions:
        rec=sex_cache.get(a) or {}
        cat=rec.get("category") or "No X/Y/Z/W label"
        sex_counts[cat]+=1
        token_counts.update(rec.get("tokens") or [])
        label_counts.update(rec.get("candidate_labels") or [])

    total=len(records)
    categories=[
        "XY labelled","ZW labelled","Other / partial label","No X/Y/Z/W label"
    ]
    payload={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "scope":"GenBank Eukaryota assemblies at chromosome or complete level",
        "mitochondrial_association":{
            "denominator":total,
            "associated":mito,
            "not_associated":total-mito,
            "percentage":100*mito/total if total else 0,
            "definition":"Assembly report contains associated organelleInfo with a description containing 'mitochond'."
        },
        "plastid_association":{
            "denominator":plants,
            "associated":plastid,
            "not_associated":plants-plastid,
            "percentage":100*plastid/plants if plants else 0,
            "denominator_definition":"Viridiplantae assemblies in the tracked collection.",
            "definition":"Assembly report contains associated organelleInfo with a description containing 'chloroplast' or 'plastid'."
        },
        "sex_chromosome_labels":{
            "denominator":total,
            "categories":[
                {"group":c,"count":sex_counts.get(c,0)} for c in categories
            ],
            "definition":"Explicit chromosome-name labels in the NCBI genome sequence report. This measures assembly labelling, not the organism's inferred biological sex-determination system.",
            "rules":{
                "XY labelled":"Both X and Y labels detected, without Z/W.",
                "ZW labelled":"Both Z and W labels detected, without X/Y.",
                "Other / partial label":"At least one X/Y/Z/W-style label detected, but not a clean XY or ZW pair.",
                "No X/Y/Z/W label":"No explicit X/Y/Z/W-style chromosome label detected."
            },
            "audit":{
                "token_counts":dict(token_counts),
                "top_candidate_labels":[{"label":k,"count":v} for k,v in label_counts.most_common(50)]
            }
        },
        "source":{
            "assembly_report":"NCBI Datasets genome assembly report (organelleInfo)",
            "sequence_report":"NCBI Datasets genome sequence report (chrName; assembled-molecule/chromosome records)",
            "taxonomy":"NCBI Taxonomy; Viridiplantae taxid 33090"
        }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    write_json(OUT,payload)
    print(f"wrote {OUT}")
    print(f"mitochondrial association: {mito}/{total} ({payload['mitochondrial_association']['percentage']:.1f}%)")
    print(f"plastid association: {plastid}/{plants} Viridiplantae ({payload['plastid_association']['percentage']:.1f}%)")
    print("sex chromosome labels:",dict(sex_counts))
    print("sex tokens:",dict(token_counts))
    print("top sex candidate labels:",label_counts.most_common(30))

if __name__=="__main__":
    main()
