#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
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
TOS_CACHE=ROOT/"cache"/"tree_of_sex_expected_20221009.json"
TOS_URL="https://raw.githubusercontent.com/sachi1n/haplodiploidy-eusociality/main/Data%20files/Trait%20data%20files/tree_of_sex_data_20221009.csv"
TOS_SOURCE_DATE="2022-10-09"
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

def load_taxonomy():
    with tempfile.TemporaryDirectory(prefix="gol_tax_") as td:
        td=Path(td); arc=td/"taxdump.tar.gz"
        req=Request(TAXDUMP_URL,headers={"User-Agent":UA})
        with urlopen(req,timeout=120) as src, arc.open("wb") as dst:
            shutil.copyfileobj(src,dst)
        with tarfile.open(arc,"r:gz") as tf:
            for basename in ("nodes.dmp","names.dmp"):
                member=next(m for m in tf.getmembers() if Path(m.name).name==basename)
                tf.extract(member,td)
        node=next(td.rglob("nodes.dmp")); names_file=next(td.rglob("names.dmp"))
        parent={}; rank={}; sci={}
        with node.open(errors="replace") as fh:
            for line in fh:
                p=line.split("|")
                if len(p)>=3:
                    tid=int(p[0].strip())
                    parent[tid]=int(p[1].strip())
                    rank[tid]=p[2].strip().casefold()
        with names_file.open(errors="replace") as fh:
            for line in fh:
                p=line.split("|")
                if len(p)>=4 and p[3].strip()=="scientific name":
                    sci[int(p[0].strip())]=p[1].strip()
        return parent,rank,sci

def taxon_lineage_by_rank(tid,parent,rank,sci):
    out={}
    cur=tid; seen=set()
    while cur and cur not in seen:
        seen.add(cur)
        r=rank.get(cur)
        if r in {"genus","family","order","class"} and r not in out:
            out[r]=sci.get(cur,"")
        nxt=parent.get(cur)
        if nxt is None or nxt==cur:break
        cur=nxt
    return out

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


def canonical_species_name(value):
    s=re.sub(r"\s+"," ",str(value or "").replace("_"," ").strip())
    if not s:
        return None
    low=f" {s.casefold()} "
    if any(x in low for x in (" hybrid "," x "," sp. "," cf. "," aff. ")):
        return None
    parts=s.split()
    if len(parts)<2:
        return None
    genus=re.sub(r"[^A-Za-z-]","",parts[0])
    species=re.sub(r"[^A-Za-z0-9.-]","",parts[1])
    if not genus or not species:
        return None
    return f"{genus.casefold()} {species.casefold()}"


def tos_system(value):
    s=re.sub(r"\s+"," ",str(value or "").strip()).casefold()
    compact=re.sub(r"[^a-z0-9]","",s)
    if not compact:
        return None
    if compact=="complexxy":
        return "complex XY"
    if compact=="complexzw":
        return "complex ZW"
    if compact in {"xy","xo","x0","zw","zo","z0","wo","w0"}:
        return {"x0":"XO","z0":"ZO","w0":"WO"}.get(compact,compact.upper())
    return None

def parse_int_values(value):
    vals=[]
    for x in re.findall(r"(?<![\d.])\d+(?![\d.])",str(value or "")):
        try:
            n=int(x)
            if 1<=n<=1000: vals.append(n)
        except ValueError:
            pass
    return sorted(set(vals))

def load_tree_of_sex_expected():
    cached=load_json(TOS_CACHE,{})
    if cached.get("source_date")==TOS_SOURCE_DATE and cached.get("species") and cached.get("inferred") and cached.get("chromosome_numbers"):
        return cached

    print("Tree of Sex: downloading source snapshot for expected sex-chromosome systems")
    resp=requests.get(TOS_URL,headers={"User-Agent":UA},timeout=180)
    resp.raise_for_status()
    by_name=defaultdict(set)
    chromosome_numbers=defaultdict(lambda: {"female":set(),"male":set()})
    ploidy=defaultdict(set)
    sexual_system=defaultdict(set)
    row_taxonomy={}
    rows=0
    for row in csv.DictReader(io.StringIO(resp.text)):
        rows+=1
        norm={str(k or "").strip().casefold():v for k,v in row.items()}
        genus=norm.get("genus") or ""
        species_epithet=norm.get("species") or ""
        name=canonical_species_name(f"{genus} {species_epithet}")
        system=tos_system(norm.get("karyotype"))
        if name:
            if system:
                by_name[name].add(system)
            for n in parse_int_values(norm.get("chromosome number (female) 2n")):
                chromosome_numbers[name]["female"].add(n)
            for n in parse_int_values(norm.get("chromosome number (male) 2n")):
                chromosome_numbers[name]["male"].add(n)
            pv=str(norm.get("predicted ploidy") or "").strip()
            sv=str(norm.get("sexual system") or "").strip()
            if pv: ploidy[name].add(pv)
            if sv: sexual_system[name].add(sv)
            row_taxonomy[name]={
                "genus":genus.strip(),
                "family":str(norm.get("family") or "").strip(),
                "order":str(norm.get("order") or "").strip(),
            }

    ambiguous=sum(1 for states in by_name.values() if len(states)>1)
    species={
        name:next(iter(states))
        for name,states in by_name.items()
        if len(states)==1
    }

    # Infer only from completely concordant Tree-of-Sex species at a named
    # genus/family/order, with increasingly strict minimum evidence upward.
    rank_min={"genus":3,"family":5,"order":10}
    rank_states={r:defaultdict(list) for r in rank_min}
    for name,system in species.items():
        tx=row_taxonomy.get(name,{})
        for r in rank_min:
            value=str(tx.get(r) or "").strip()
            if value:
                rank_states[r][value.casefold()].append(system)
    def inference_system(states):
        groups={expected_group(x) for x in states}
        groups.discard(None)
        if len(groups)!=1:
            return None
        group=next(iter(groups))
        return {
            "XY / complex XY":"XY",
            "ZW / complex ZW":"ZW",
            "XO":"XO",
            "ZO / WO":None,
        }.get(group)

    inferred={}
    for r,min_n in rank_min.items():
        inferred[r]={}
        for taxon,states in rank_states[r].items():
            consensus=inference_system(states)
            if len(states)>=min_n and consensus:
                inferred[r][taxon]={"system":consensus,"support_species":len(states)}

    out={
        "source_date":TOS_SOURCE_DATE,
        "source_url":TOS_URL,
        "rows_read":rows,
        "ambiguous_species_excluded":ambiguous,
        "species":species,
        "chromosome_numbers":{
            name:{
                "female":sorted(v["female"]),
                "male":sorted(v["male"]),
            }
            for name,v in chromosome_numbers.items()
            if v["female"] or v["male"]
        },
        "ploidy":{
            name:sorted(v) for name,v in ploidy.items() if len(v)==1
        },
        "sexual_system":{
            name:sorted(v) for name,v in sexual_system.items() if len(v)==1
        },
        "inferred":inferred,
        "inference_rule":"Higher-rank expectations require complete concordance among Tree of Sex species: >=3 species/genus, >=5/family, >=10/order.",
    }
    write_json(TOS_CACHE,out)
    print(
        f"Tree of Sex: cached {len(species)} unambiguous species "
        f"({ambiguous} conflicting species excluded)"
    )
    return out


def expected_group(system):
    if system in {"XY","complex XY"}:
        return "XY / complex XY"
    if system=="XO":
        return "XO"
    if system in {"ZW","complex ZW"}:
        return "ZW / complex ZW"
    if system in {"ZO","WO"}:
        return "ZO / WO"
    return None


def observed_matches_expected(system,tokens):
    t=set(tokens)
    if system in {"XY","complex XY"}:
        return {"X","Y"}<=t
    if system=="XO":
        return "X" in t
    if system in {"ZW","complex ZW"}:
        return {"Z","W"}<=t
    if system=="ZO":
        return "Z" in t
    if system=="WO":
        return "W" in t
    return False


def build_expected_vs_observed(records,effective_tokens,parent,rank,sci):
    tos=load_tree_of_sex_expected()
    lookup=tos.get("species") or {}
    counts=defaultdict(Counter)
    matched_species=set()
    matched_assemblies=0
    provenance=Counter()

    for rec in records:
        name=canonical_species_name(rec.get("organism_name"))
        system=lookup.get(name) if name else None
        source="species documented" if system else None
        if not system and rec.get("taxid"):
            lineage=taxon_lineage_by_rank(rec["taxid"],parent,rank,sci)
            for r in ("genus","family","order"):
                taxon=str(lineage.get(r) or "").casefold()
                hit=((tos.get("inferred") or {}).get(r) or {}).get(taxon)
                if hit:
                    system=hit["system"]
                    source=f"{r} inferred"
                    break
            # Birds are unusually conserved for female heterogamety and Tree
            # of Sex explicitly notes their uniform sex-determination system.
            if not system and is_desc(rec["taxid"],8782,parent,{}):
                system="ZW"
                source="Aves inferred"
        group=expected_group(system)
        if not system or not group:
            continue
        matched_assemblies+=1
        matched_species.add(name or str(rec.get("taxid")))
        provenance[source]+=1
        toks=set(effective_tokens.get(rec["accession"]) or [])
        if observed_matches_expected(system,toks):
            status="Expected label(s) found"
        elif toks:
            status="Partial / different label"
        else:
            status="No sex-chromosome label"
        counts[group][status]+=1

    order=["XY / complex XY","XO","ZW / complex ZW","ZO / WO"]
    statuses=[
        "Expected label(s) found",
        "Partial / different label",
        "No sex-chromosome label",
    ]
    groups=[]
    for group in order:
        total=sum(counts[group].values())
        if not total:
            continue
        groups.append({
            "expected":group,
            "assemblies":total,
            "observed":[
                {"group":status,"count":counts[group].get(status,0)}
                for status in statuses
            ],
        })

    return {
        "matched_assemblies":matched_assemblies,
        "matched_species":len(matched_species),
        "tree_of_sex_species_with_unambiguous_karyotype":len(lookup),
        "ambiguous_tree_of_sex_species_excluded":tos.get("ambiguous_species_excluded",0),
        "source_snapshot":TOS_SOURCE_DATE,
        "provenance":dict(provenance),
        "groups":groups,
        "definition":"Assembly-level comparison for chromosome/complete GenBank genomes. Expectations use an explicit Tree of Sex species karyotype first, then only fully concordant genus/family/order Tree-of-Sex evidence; Aves may inherit ZW because Tree of Sex explicitly describes birds as uniform in sex-determination system. Observed labels come from NCBI sequence reports.",
        "rules":{
            "XY / complex XY":"Expected when both X and Y labels are observed.",
            "XO":"Expected when an X label is observed.",
            "ZW / complex ZW":"Expected when both Z and W labels are observed.",
            "ZO / WO":"Expected when the corresponding Z or W label is observed.",
        },
    }


def build_karyotype_audit(records):
    tos=load_tree_of_sex_expected()
    chrom=tos.get("chromosome_numbers") or {}
    bins=Counter(); matched_species=set(); matched=0
    ploidy_counts=Counter()
    sexual_counts=Counter()
    for rec in records:
        name=canonical_species_name(rec.get("organism_name"))
        if not name: continue
        expected=chrom.get(name) or {}
        vals=sorted(set((expected.get("female") or [])+(expected.get("male") or [])))
        try: observed=int(rec.get("assembly_chromosomes"))
        except (TypeError,ValueError): observed=None
        if vals and observed:
            # Tree of Sex gives diploid counts while a haploid assembly often
            # represents one homolog per autosome. Compare to both 2N and N,
            # and use whichever is closer; report as broad agreement only.
            candidates=set(vals)
            candidates.update(n/2 for n in vals if n%2==0)
            rel=min(abs(observed-x)/x for x in candidates if x>0)
            matched+=1; matched_species.add(name)
            if rel<=0.05: bins["Within 5%"]+=1
            elif rel<=0.20: bins["Within 20%"]+=1
            else: bins[">20% different"]+=1
        if name in (tos.get("ploidy") or {}):
            ploidy_counts.update((tos["ploidy"][name][0],))
        if name in (tos.get("sexual_system") or {}):
            sexual_counts.update((tos["sexual_system"][name][0],))
    return {
        "matched_assemblies":matched,
        "matched_species":len(matched_species),
        "categories":[{"group":k,"count":bins[k]} for k in ("Within 5%","Within 20%",">20% different")],
        "definition":"Observed NCBI total chromosome count compared with Tree of Sex female/male 2N values. Because assemblies can represent a haploid chromosome complement, agreement is assessed against both reported 2N and N where 2N is even; the closer expectation is used.",
        "tree_of_sex_traits":{
            "ploidy_species":len(tos.get("ploidy") or {}),
            "sexual_system_species":len(tos.get("sexual_system") or {}),
            "top_ploidy":[{"group":k,"count":v} for k,v in ploidy_counts.most_common(8)],
            "top_sexual_system":[{"group":k,"count":v} for k,v in sexual_counts.most_common(8)],
        }
    }

def build_assembly_quality(records):
    lengths=[]; n50s=[]; chroms=[]
    for rec in records:
        try: lengths.append(int(rec.get("assembly_length")))
        except (TypeError,ValueError): pass
        try: n50s.append(int(rec.get("contig_n50")))
        except (TypeError,ValueError): pass
        try: chroms.append(int(rec.get("assembly_chromosomes")))
        except (TypeError,ValueError): pass
    def median(xs):
        if not xs:return None
        ys=sorted(xs); n=len(ys)
        return ys[n//2] if n%2 else (ys[n//2-1]+ys[n//2])/2
    size_edges_mb=[1,3,10,30,100,300,1000,3000,10000,30000,100000]
    size_counts=[0]*(len(size_edges_mb)+1)
    for bp in lengths:
        mb=bp/1_000_000
        idx=next((i for i,e in enumerate(size_edges_mb) if mb<e),len(size_edges_mb))
        size_counts[idx]+=1
    size_hist=[]
    lows=[0]+size_edges_mb
    highs=size_edges_mb+[None]
    for i,count in enumerate(size_counts):
        lo=lows[i]; hi=highs[i]
        label=(f"<{hi:g} Mb" if i==0 else f"{lo:g}–{hi:g} Mb" if hi is not None else f"≥{lo:g} Mb")
        size_hist.append({"label":label,"count":count})

    chrom_edges=[1,5,10,20,30,40,50,75,100]
    chrom_counts=[0]*(len(chrom_edges)+1)
    for n in chroms:
        idx=next((i for i,e in enumerate(chrom_edges) if n<=e),len(chrom_edges))
        chrom_counts[idx]+=1
    chrom_labels=["1","2–5","6–10","11–20","21–30","31–40","41–50","51–75","76–100",">100"]
    chrom_hist=[{"label":label,"count":count} for label,count in zip(chrom_labels,chrom_counts)]

    return {
        "assemblies":len(records),
        "median_assembly_size_bp":median(lengths),
        "median_contig_n50_bp":median(n50s),
        "median_chromosomes_reported":median(chroms),
        "assembly_size_available":len(lengths),
        "contig_n50_available":len(n50s),
        "chromosome_count_available":len(chroms),
        "assembly_size_histogram":size_hist,
        "chromosome_count_histogram":chrom_hist,
        "definition":"Current NCBI assembly statistics for the tracked chromosome-scale/complete GenBank collection."
    }


TECH_RULES=[
    ("Illumina", r"\billumina\b|\bnovaseq\b|\bhiseq\b|\bmiseq\b|\bnextseq\b|\biseq\b"),
    ("PacBio HiFi", r"\bhifi\b|\bccs\b|circular consensus|\brevio\b|\bci[- ]?fi\b"),
    ("Oxford Nanopore", r"\boxford nanopore\b|\bnanopore\b|\bminion\b|\bpromethion\b|\bgridion\b"),
    ("10x Genomics", r"\b10x\b|\b10 x\b|10x genomics|linked[- ]?read|\bchromium\b"),
    ("BGI / MGI", r"\bbgi\b|\bmgi\b|\bdnbseq\b|\bmgiseq\b"),
    ("Sanger", r"\bsanger\b|capillary sequencing|\babi[ -]?3730\b"),
    ("Ion Torrent", r"\bion torrent\b|\bion proton\b"),
    ("SOLiD", r"\bsolid\b"),
]
PROXIMITY_RE=re.compile(
    r"\bhi[- ]?c\b|\bomni[- ]?c\b|\bdovetail\b|\barima\d*\b|"
    r"phase genomics|\bchicago\b|\bci[- ]?fi\b",
    re.I,
)
ASSEMBLER_RULES=[
    ("hifiasm", r"\bhifiasm\b"),
    ("Canu / HiCanu", r"\bhicanu\b|\bcanu\b"),
    ("FALCON", r"\bfalcon(?:[-_ ]?unzip)?\b"),
    ("Flye", r"\bmetaflye\b|\bflye\b"),
    ("Verkko", r"\bverkko\d*\b"),
    ("MaSuRCA", r"\bmasurca\b|\bma[- ]?su[- ]?r?ca\b"),
    ("ALLPATHS-LG", r"\ballpaths(?:[-_ ]?lg)?\b"),
    ("SOAPdenovo", r"\bsoapdenovo(?:2)?\b"),
    ("SPAdes", r"\bspades\b"),
    ("Supernova", r"\bsupernova\b"),
    ("ABySS", r"\babyss\b"),
    ("DISCOVAR", r"\bdiscovar\b"),
    ("wtdbg2 / Redbean", r"\bwtdbg2\b|\bredbean\b"),
    ("Shasta", r"\bshasta\b"),
    ("Velvet", r"\bvelvet\b"),
    ("Newbler / GS De Novo", r"\bnewbler\b|gs de novo assembler"),
    ("IDBA", r"\bidba(?:[_-]?ud)?\b"),
    ("TRITEX", r"\btritex\b"),
    ("NextDenovo", r"\bnextdenovo\b"),
    ("Geneious", r"\bgeneious\b"),
]

def metadata_text(value):
    if value is None:
        return ""
    if isinstance(value,list):
        return "; ".join(str(x) for x in value if x not in (None,""))
    if isinstance(value,dict):
        return "; ".join(str(x) for x in value.values() if x not in (None,""))
    return str(value)

def classify_sequencing_tech(value):
    raw=metadata_text(value)
    s=raw.casefold()
    if not s.strip():
        return set()
    out=set()
    hifi=bool(re.search(TECH_RULES[1][1],s))
    for label,pat in TECH_RULES:
        if label=="PacBio HiFi":
            if hifi: out.add(label)
        elif re.search(pat,s):
            out.add(label)
    # PacBio records often omit whether reads were generated in CLR vs HiFi/CCS mode.
    # Do not infer a non-HiFi technology from that absence; keep these as
    # "HiFi not specified" unless the record explicitly identifies HiFi/CCS/Revio/CiFi.
    if not hifi and re.search(r"\bpacbio\b|\bpacific biosciences\b|\bsmrt\b|\bsequel\b|\brs ?ii\b",s):
        out.add("PacBio (HiFi not specified)")
    return out

def uses_proximity_scaffolding(value):
    return bool(PROXIMITY_RE.search(metadata_text(value)))

def classify_assembly_method(value):
    s=metadata_text(value).casefold()
    if not s.strip():
        return set()
    return {label for label,pat in ASSEMBLER_RULES if re.search(pat,s)}

def release_year(value):
    m=re.match(r"^(\d{4})",str(value or ""))
    if not m:
        return None
    y=int(m.group(1))
    now=datetime.now(timezone.utc).year
    return y if 1990<=y<=now else None

def build_method_trends(records):
    years=defaultdict(lambda:{
        "assemblies":0,
        "tech_reported":0,
        "assembler_reported":0,
        "proximity":0,
        "tech":Counter(),
        "assemblers":Counter(),
        "tech_unclassified":0,
        "assembler_unclassified":0,
    })
    raw_tech=Counter()
    raw_methods=Counter()

    for rec in records:
        year=release_year(rec.get("release_date"))
        if year is None:
            continue
        y=years[year]
        y["assemblies"]+=1

        tech_raw=metadata_text(rec.get("sequencing_tech")).strip()
        if tech_raw:
            y["tech_reported"]+=1
            raw_tech[tech_raw]+=1
            if uses_proximity_scaffolding(tech_raw):
                y["proximity"]+=1
            cats=classify_sequencing_tech(tech_raw)
            if cats:
                y["tech"].update(cats)
            else:
                # Proximity-only metadata is not a primary sequencing
                # technology, so do not call it an unclassified technology.
                if not uses_proximity_scaffolding(tech_raw):
                    y["tech_unclassified"]+=1

        method_raw=metadata_text(rec.get("assembly_method")).strip()
        method_low=method_raw.casefold()
        # NCBI contains thousands of legacy records whose assemblyMethod is
        # literally "various". Treat those as missing for prevalence trends:
        # they are non-empty metadata but do not identify an assembler.
        method_informative=bool(method_raw) and method_low not in {
            "various","unknown","unspecified","not provided","n/a","na","none","-"
        }
        if method_raw:
            raw_methods[method_raw]+=1
        if method_informative:
            y["assembler_reported"]+=1
            cats=classify_assembly_method(method_raw)
            if cats:
                y["assemblers"].update(cats)
            else:
                y["assembler_unclassified"]+=1

    tech_totals=Counter()
    assembler_totals=Counter()
    for y in years.values():
        tech_totals.update(y["tech"])
        assembler_totals.update(y["assemblers"])

    # Keep all normalized technology families; limit assembler lines to the
    # most represented named assembler families so the browser chart stays legible.
    tech_series=[
        x for x,_ in sorted(tech_totals.items(), key=lambda kv:(-kv[1],kv[0]))
    ]
    assembler_series=[
        x for x,_ in sorted(assembler_totals.items(), key=lambda kv:(-kv[1],kv[0]))[:8]
    ]

    rows=[]
    for year in sorted(years):
        y=years[year]
        rows.append({
            "year":year,
            "assemblies":y["assemblies"],
            "tech_reported":y["tech_reported"],
            "assembler_reported":y["assembler_reported"],
            "proximity":y["proximity"],
            "tech_unclassified":y["tech_unclassified"],
            "assembler_unclassified":y["assembler_unclassified"],
            "technology":{k:y["tech"].get(k,0) for k in tech_series},
            "assemblers":{k:y["assemblers"].get(k,0) for k in assembler_series},
        })

    return {
        "years":rows,
        "technology_series":tech_series,
        "proximity_series":["Hi-C / proximity"],
        "assembler_series":assembler_series,
        "technology_metadata_assemblies":sum(y["tech_reported"] for y in years.values()),
        "proximity_assemblies":sum(y["proximity"] for y in years.values()),
        "assembler_metadata_assemblies":sum(y["assembler_reported"] for y in years.values()),
        "technology_unclassified_assemblies":sum(y["tech_unclassified"] for y in years.values()),
        "assembler_unclassified_assemblies":sum(y["assembler_unclassified"] for y in years.values()),
        "top_raw_sequencing_tech":[{"value":k,"count":v} for k,v in raw_tech.most_common(25)],
        "top_raw_assembly_methods":[{"value":k,"count":v} for k,v in raw_methods.most_common(25)],
        "definition":"Year is the NCBI assembly release year. Primary sequencing-technology lines use assemblies with non-empty sequencingTech metadata and exclude Hi-C/proximity-ligation methods from that classification. Proximity use is tracked independently from the same metadata field. Assembler lines use assemblies with an informative assemblyMethod value (generic values such as 'various' are treated as missing). One assembly can contribute to multiple primary technology lines when hybrid sequencing was reported.",
    }

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
    # Sanitize the first historical cache generated during development.
    # Bare U/V labels are too ambiguous because they are commonly ordinary
    # Roman-numeral chromosomes; retain U/V only when future incremental
    # sequence reports explicitly identify them in a sex-chromosome context.
    sanitized=0
    for acc,rec in list(cache.items()):
        toks=set(rec.get("tokens") or [])
        cleaned=toks-{"U","V"}
        labels=list(rec.get("candidate_labels") or [])
        cleaned_labels=[
            x for x in labels
            if str(x).strip().upper() not in {"U","V"}
        ]
        if cleaned!=toks or cleaned_labels!=labels:
            rec=dict(rec)
            rec["tokens"]=sorted(cleaned)
            rec["candidate_labels"]=cleaned_labels
            rec["category"]=classify_tokens(cleaned)
            cache[acc]=rec
            sanitized+=1
    if sanitized:
        print(f"sex labels: sanitized ambiguous bare U/V metadata in {sanitized} cached assemblies")
        write_json(CACHE,cache)

    missing=[a for a in accessions if a not in cache]
    cached_tokens=sum(
        bool((cache.get(a) or {}).get("tokens"))
        for a in accessions
    )

    # First historical fill or recovery from a genuinely empty cache.
    if len(missing)>1000 or (accessions and cached_tokens==0):
        print(
            f"sex labels: filtered metadata-package bootstrap for "
            f"{len(accessions)} assemblies (replacing {len(cache)} cached records)"
        )
        cache=bootstrap_sex_cache_package(accessions)
        write_json(CACHE,cache)
        return cache

    if not missing:
        return cache

    # Daily incremental fill: new assemblies are few, so one CLI query over
    # an accession file is cheap and returns the complete chromosome labels.
    print(
        f"sex labels: resolving {len(missing)} newly deposited assemblies "
        f"through one NCBI sequence-report query"
    )
    cache.update(resolve_sex_batch(missing))
    write_json(CACHE,cache)
    return cache


def main():
    parent,rank,sci=load_taxonomy(); lineage_cache={}
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

        organism_name=str(first(
            r,"organism.organism_name","organism.organismName",
            "organism.scientific_name","organism.scientificName",
            default=""
        ) or "")
        records.append({
            "accession":acc,"taxid":taxid,"organism_name":organism_name,
            "assembly_chromosomes":first(r,"assembly_stats.total_number_of_chromosomes","assemblyStats.totalNumberOfChromosomes"),
            "assembly_length":first(r,"assembly_stats.total_sequence_length","assemblyStats.totalSequenceLength"),
            "contig_n50":first(r,"assembly_stats.contig_n50","assemblyStats.contigN50"),
            "scaffold_n50":first(r,"assembly_stats.scaffold_n50","assemblyStats.scaffoldN50"),
            "release_date":first(r,"assembly_info.release_date","assemblyInfo.releaseDate"),
            "sequencing_tech":first(r,"assembly_info.sequencing_tech","assemblyInfo.sequencingTech"),
            "assembly_method":first(r,"assembly_info.assembly_method","assemblyInfo.assemblyMethod"),
        })

    accessions=[x["accession"] for x in records]
    sex_cache=load_json(CACHE,{})
    sex_cache=build_sex_cache(accessions,sex_cache)

    sex_counts=Counter()
    token_counts=Counter()
    label_counts=Counter()
    taxid_by_accession={x["accession"]:x["taxid"] for x in records}
    fungal_x_only=0
    effective_tokens={}
    for a in accessions:
        rec=sex_cache.get(a) or {}
        toks=set(rec.get("tokens") or [])
        taxid=taxid_by_accession.get(a)
        # In fungi, a bare chromosome X is commonly Roman numeral ten rather
        # than a sex chromosome. Exclude X-only fungal records unless another
        # explicit sex-style token is present.
        if toks=={"X"} and taxid and is_desc(taxid,FUNGI,parent,lineage_cache):
            toks=set()
            cat="No sex-chromosome label"
            fungal_x_only+=1
        else:
            cat=classify_tokens(toks)
            token_counts.update(toks)
            label_counts.update(rec.get("candidate_labels") or [])
        effective_tokens[a]=sorted(toks)
        sex_counts[cat]+=1

    try:
        expected_vs_observed=build_expected_vs_observed(records,effective_tokens,parent,rank,sci)
    except Exception as exc:
        print(f"WARNING: Tree of Sex comparison unavailable: {exc}")
        expected_vs_observed=None

    karyotype_audit=build_karyotype_audit(records)
    assembly_quality=build_assembly_quality(records)
    method_trends=build_method_trends(records)

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
        "sex_chromosome_expected_vs_observed":expected_vs_observed,
        "karyotype_audit":karyotype_audit,
        "assembly_quality":assembly_quality,
        "methods_through_time":method_trends,
        "source":{
            "assembly_report":"NCBI Datasets genome assembly report (organelleInfo; assemblyInfo.releaseDate; assemblyInfo.sequencingTech; assemblyInfo.assemblyMethod)",
            "sequence_report":"NCBI Datasets genome sequence report (chrName; assembled-molecule/chromosome records)",
            "taxonomy":"NCBI Taxonomy; Viridiplantae taxid 33090",
            "tree_of_sex":"Tree of Sex karyotype snapshot dated 2022-10-09; original database described by The Tree of Sex Consortium (2014), Scientific Data 1:140015."
        }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    write_json(OUT,payload)
    print(f"wrote {OUT}")
    print(f"mitochondrial association: {mito}/{total} ({payload['mitochondrial_association']['percentage']:.1f}%)")
    print(f"plastid association: {plastid}/{plants} Viridiplantae ({payload['plastid_association']['percentage']:.1f}%)")
    print("sex chromosome labels:",dict(sex_counts))
    if expected_vs_observed:
        print(
            "Tree of Sex matched:",
            expected_vs_observed["matched_assemblies"],"assemblies from",
            expected_vs_observed["matched_species"],"species"
        )
    print("sex tokens:",dict(token_counts))
    print("top sex candidate labels:",label_counts.most_common(30))

if __name__=="__main__":
    main()
