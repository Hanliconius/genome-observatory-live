#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import requests
import shutil
import subprocess
import tarfile
import time
import tempfile
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import zipfile
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
# Genometrics bootstrap version: 3
VIRIDIPLANTAE=33090
FUNGI=4751
BATCH_SIZE=250
SEQUENCE_REPORT_URL="https://api.ncbi.nlm.nih.gov/datasets/v2/genome/sequence_reports"
EUTILS_BASE="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ACCESSION_RE=re.compile(r"\bGC[AF]_\d+(?:\.\d+)?\b")
SEX_CHROMOSOME_QUERY=(
    ["X","Y","Z","W","U","V"]
    + [f"{base}{i}" for base in ("X","Y","Z","W","U","V") for i in range(1,10)]
    + [f"LG{base}" for base in ("X","Y","Z","W","U","V")]
    + ["sex chromosome","gonosome"]
)

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
    """Return an explicit sex-chromosome-style token from a chromosome label."""
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

    if re.search(r"SEX[ _.-]*CHROM|GONOSOM",s):
        m=re.search(r"(?:^|[^A-Z])([XYZWUV])(?:[^A-Z]|$)",s)
        return m.group(1) if m else "OTHER"
    return None

def classify_tokens(tokens):
    t=set(tokens)
    biological=t-{"OTHER"}
    if {"X","Y"}<=biological and not ({"Z","W","U","V"} & biological):
        return "XY labelled"
    if {"Z","W"}<=biological and not ({"X","Y","U","V"} & biological):
        return "ZW labelled"
    if t:
        return "Other / partial label"
    return "No sex-chromosome label"


def sequence_report_page(batch,page_token=None):
    body={
        "accession": ",".join(batch),
        "chromosomes": SEX_CHROMOSOME_QUERY,
        "page_size": 1000,
    }
    if page_token:
        body["page_token"]=page_token

    last=None
    for attempt in range(10):
        try:
            time.sleep(0.5)
            resp=requests.post(
                SEQUENCE_REPORT_URL,
                json=body,
                headers={
                    "Accept":"application/json",
                    "User-Agent":UA,
                },
                timeout=90,
            )
            if resp.status_code in {429,500,502,503,504}:
                last=RuntimeError(f"NCBI sequence-report HTTP {resp.status_code}")
                if resp.status_code==429:
                    retry=resp.headers.get("Retry-After")
                    try:
                        delay=max(3.0,float(retry)) if retry else min(30.0,3.0*(attempt+1))
                    except ValueError:
                        delay=min(30.0,3.0*(attempt+1))
                else:
                    delay=min(20.0,2.0*(attempt+1))
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException,ValueError) as exc:
            last=exc
            time.sleep(2.0*(attempt+1))
    raise RuntimeError(f"NCBI sequence-report request failed after retries: {last}")


def resolve_sex_batch(batch):
    labels=defaultdict(set)
    tokens=defaultdict(set)
    with tempfile.NamedTemporaryFile("w",delete=False,prefix="gol_acc_",suffix=".txt") as fh:
        for a in batch:
            fh.write(a+"\n")
        path=fh.name
    try:
        cmd=[
            "datasets","summary","genome","accession",
            "--inputfile",path,
            "--report","sequence",
            "--as-json-lines",
        ]
        for r in stream(cmd):
            a=str(first(r,"assembly_accession","assemblyAccession","accession",default="") or "")
            role=str(first(r,"role",default="") or "").casefold()
            loc=str(first(r,"assigned_molecule_location_type","assignedMoleculeLocationType",default="") or "").casefold()
            if not a or not (role=="assembled-molecule" or loc=="chromosome"):
                continue
            c=normalize_chr_label(first(r,"chr_name","chrName",default=""))
            if not c:
                continue
            labels[a].add(c)
            tok=sex_token(c)
            if tok:
                tokens[a].add(tok)
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


def eutils_json(endpoint,params,post=False):
    encoded=urllib.parse.urlencode(params).encode()
    if post:
        req=urllib.request.Request(
            EUTILS_BASE+endpoint,data=encoded,headers={"User-Agent":UA}
        )
    else:
        req=urllib.request.Request(
            EUTILS_BASE+endpoint+"?"+encoded.decode(),headers={"User-Agent":UA}
        )
    with urllib.request.urlopen(req,timeout=180) as resp:
        return json.loads(resp.read().decode())


def eutils_xml(endpoint,params):
    encoded=urllib.parse.urlencode(params).encode()
    req=urllib.request.Request(
        EUTILS_BASE+endpoint,data=encoded,headers={"User-Agent":UA}
    )
    with urllib.request.urlopen(req,timeout=180) as resp:
        return ET.fromstring(resp.read())


def collect_accession_strings(value,out):
    if isinstance(value,dict):
        for v in value.values():
            collect_accession_strings(v,out)
    elif isinstance(value,list):
        for v in value:
            collect_accession_strings(v,out)
    elif isinstance(value,str):
        out.update(ACCESSION_RE.findall(value))


def search_nucleotide_ids(title_terms):
    clauses=[f'"{term}"[Title]' for term in title_terms]
    term="Eukaryota[Organism] AND ("+" OR ".join(clauses)+")"
    page=eutils_json(
        "esearch.fcgi",
        {
            "db":"nuccore","term":term,"retmode":"json",
            "retmax":"100000","tool":"GenomeObservatoryLive"
        }
    )
    result=page.get("esearchresult") or {}
    ids=list(result.get("idlist") or [])
    count=int(result.get("count") or 0)
    for offset in range(len(ids),count,100000):
        time.sleep(.36)
        extra=eutils_json(
            "esearch.fcgi",
            {
                "db":"nuccore","term":term,"retmode":"json",
                "retmax":"100000","retstart":str(offset),
                "tool":"GenomeObservatoryLive"
            }
        )
        ids.extend((extra.get("esearchresult") or {}).get("idlist") or [])
    return ids


def linked_assembly_ids(nucleotide_ids):
    out=set()
    for i in range(0,len(nucleotide_ids),400):
        time.sleep(.36)
        root=eutils_xml(
            "elink.fcgi",
            {
                "dbfrom":"nuccore","db":"assembly",
                "id":",".join(nucleotide_ids[i:i+400]),
                "tool":"GenomeObservatoryLive"
            }
        )
        for block in root.findall(".//LinkSetDb"):
            name=(block.findtext("LinkName") or "").casefold()
            dbto=(block.findtext("DbTo") or "").casefold()
            if "assembly" not in name and dbto!="assembly":
                continue
            for node in block.findall("./Link/Id"):
                if node.text:
                    out.add(node.text.strip())
    return sorted(out)


def assembly_aliases(assembly_ids):
    aliases=set()
    for i in range(0,len(assembly_ids),400):
        time.sleep(.36)
        d=eutils_json(
            "esummary.fcgi",
            {
                "db":"assembly","id":",".join(assembly_ids[i:i+400]),
                "retmode":"json","tool":"GenomeObservatoryLive"
            },
            post=True
        )
        result=d.get("result") or {}
        for uid in result.get("uids",[]) or []:
            collect_accession_strings(result.get(str(uid)) or {},aliases)
    return aliases


def bootstrap_sex_cache_entrez(accessions):
    tracked=set(accessions)
    tokens=defaultdict(set)
    audits={}
    queries={
        "X":["chromosome X","chromosome X1","chromosome X2"],
        "Y":["chromosome Y","chromosome Y1","chromosome Y2"],
        "Z":["chromosome Z","chromosome Z1","chromosome Z2"],
        "W":["chromosome W","chromosome W1","chromosome W2"],
        "OTHER":["sex chromosome","gonosome","U sex chromosome","V sex chromosome"],
    }

    for token,title_terms in queries.items():
        ids=search_nucleotide_ids(title_terms)
        assembly_ids=linked_assembly_ids(ids) if ids else []
        aliases=assembly_aliases(assembly_ids) if assembly_ids else set()
        hits=tracked & aliases
        for acc in hits:
            tokens[acc].add(token)
        audits[token]={
            "nucleotide_records":len(ids),
            "linked_assembly_ids":len(assembly_ids),
            "tracked_genbank_assemblies":len(hits),
        }
        print(
            f"sex labels: {token} -> {len(ids)} nucleotide records, "
            f"{len(assembly_ids)} linked assemblies, {len(hits)} tracked GenBank assemblies"
        )

    out={}
    for acc in accessions:
        toks=sorted(tokens.get(acc,set()))
        out[acc]={
            "category":classify_tokens(toks),
            "tokens":toks,
            "candidate_labels":toks,
        }
    print("sex labels: Entrez bootstrap audit",json.dumps(audits,sort_keys=True))
    return out


def bootstrap_sex_cache_package(accessions):
    """One-time historical fill from an NCBI metadata-only package."""
    labels=defaultdict(set)
    tokens=defaultdict(set)

    with tempfile.TemporaryDirectory(prefix="gol_sex_package_") as td:
        td=Path(td)
        accfile=td/"accessions.txt"
        zpath=td/"sex_sequence_reports.zip"
        accfile.write_text("\n".join(accessions)+"\n")

        cmd=[
            "datasets","download","genome","accession",
            "--inputfile",str(accfile),
            "--chromosomes",",".join(SEX_CHROMOSOME_QUERY),
            "--include","seq-report",
            "--filename",str(zpath),
            "--no-progressbar",
            "--fast-zip-validation",
        ]
        print(
            f"sex labels: requesting one filtered metadata package for "
            f"{len(accessions)} tracked assemblies"
        )
        p=subprocess.run(cmd,text=True,capture_output=True)
        if p.returncode:
            raise RuntimeError(
                f"datasets filtered sex-report package failed {p.returncode}: "
                f"{p.stderr[-6000:]}"
            )

        with zipfile.ZipFile(zpath) as zf:
            names=[
                n for n in zf.namelist()
                if n.endswith("/sequence_report.jsonl")
            ]
            print(f"sex labels: package contains {len(names)} matching assembly reports")
            for name in names:
                with zf.open(name) as fh:
                    for raw in fh:
                        try:
                            r=json.loads(raw)
                        except Exception:
                            continue
                        a=str(first(
                            r,"assembly_accession","assemblyAccession","accession",
                            default=""
                        ) or "")
                        if not a:
                            continue
                        role=str(first(r,"role",default="") or "").casefold()
                        loc=str(first(
                            r,"assigned_molecule_location_type",
                            "assignedMoleculeLocationType",default=""
                        ) or "").casefold()
                        if role!="assembled-molecule" and loc!="chromosome":
                            continue
                        c=normalize_chr_label(first(r,"chr_name","chrName",default=""))
                        if not c:
                            continue
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
    cached_tokens=sum(
        bool((cache.get(a) or {}).get("tokens"))
        for a in accessions
    )

    # Rebuild the known-bad all-empty bootstrap cache, or do the first
    # historical fill, from one filtered metadata package.
    if len(missing)>1000 or (accessions and cached_tokens==0):
        print(
            f"sex labels: package bootstrap for {len(accessions)} assemblies "
            f"(replacing {len(cache)} cached records)"
        )
        cache=bootstrap_sex_cache_package(accessions)
        write_json(CACHE,cache)
        return cache

    if not missing:
        return cache

    # Daily incremental fill: new assemblies are few, so a single CLI
    # sequence-report query is cheap and avoids maintaining another package.
    print(
        f"sex labels: resolving {len(missing)} newly deposited assemblies "
        f"through one NCBI sequence-report query"
    )
    cache.update(resolve_sex_batch(missing))
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
    taxid_by_accession={x["accession"]:x["taxid"] for x in records}
    fungal_x_only=0
    for a in accessions:
        rec=sex_cache.get(a) or {}
        toks=set(rec.get("tokens") or [])
        taxid=taxid_by_accession.get(a)
        # In fungi, a bare chromosome X is commonly Roman numeral ten rather
        # than a sex chromosome. Exclude X-only fungal records unless another
        # explicit sex-style token is present.
        if toks=={"X"} and taxid and is_desc(taxid,FUNGI,parent,lineage_cache):
            cat="No sex-chromosome label"
            fungal_x_only+=1
        else:
            cat=rec.get("category") or "No sex-chromosome label"
            token_counts.update(toks)
            label_counts.update(rec.get("candidate_labels") or [])
        sex_counts[cat]+=1

    total=len(records)
    categories=[
        "XY labelled","ZW labelled","Other / partial label","No sex-chromosome label"
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
            "definition":"Explicit chromosome-name labels in the NCBI genome sequence report. This includes X/Y/Z/W-style and explicitly identified other sex-chromosome labels and measures assembly labelling, not the organism's inferred biological sex-determination system.",
            "rules":{
                "XY labelled":"Both X and Y labels detected, without Z/W.",
                "ZW labelled":"Both Z and W labels detected, without X/Y.",
                "Other / partial label":"At least one X/Y/Z/W-style or explicitly identified other sex-chromosome label detected, but not a clean XY or ZW pair.",
                "No sex-chromosome label":"No explicit X/Y/Z/W-style or explicitly identified other sex-chromosome label detected."
            },
            "audit":{
                "token_counts":dict(token_counts),
                "top_candidate_labels":[{"label":k,"count":v} for k,v in label_counts.most_common(50)],
                "excluded_fungal_x_only":fungal_x_only
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
