#!/usr/bin/env python3
import json, subprocess
from collections import Counter

def first(d,*paths,default=None):
    for path in paths:
        x=d
        try:
            for k in path.split("."):
                x=x[int(k)] if isinstance(x,list) else x[k]
            if x not in (None,""): return x
        except (KeyError,IndexError,TypeError,ValueError):
            pass
    return default

cmd=[
    "datasets","summary","genome","taxon","Eukaryota",
    "--assembly-source","GenBank",
    "--assembly-level","chromosome,complete",
    "--as-json-lines"
]
p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
counts=Counter()
owners=Counter()
submitters=Counter()
attr_names=Counter()
n=0
has_seq=0
assert p.stdout is not None
for line in p.stdout:
    line=line.strip()
    if not line: continue
    n+=1
    r=json.loads(line)
    bs=first(r,"assembly_info.biosample","assemblyInfo.biosample",default={}) or {}
    seq=[]
    for a in bs.get("attributes",[]) or []:
        name=str(a.get("name","")).strip().casefold().replace("-","_").replace(" ","_")
        if "sequenc" in name:
            attr_names[name]+=1
        if name in {"sequenced_by","sequencedby"}:
            v=str(a.get("value","")).strip()
            if v: seq.append(v)
    if seq:
        has_seq+=1
        for v in seq: counts[v]+=1
    owner=first(bs,"owner.name",default="")
    if owner: owners[str(owner).strip()]+=1
    sub=first(r,"assembly_info.submitter","assemblyInfo.submitter",default="")
    if sub: submitters[str(sub).strip()]+=1

stderr=p.stderr.read() if p.stderr else ""
code=p.wait()
if code:
    raise SystemExit(stderr[-4000:])

print("ASSEMBLIES",n)
print("HAS_SEQUENCED_BY",has_seq)
print("FRACTION",has_seq/n if n else 0)
print("DISTINCT_SEQUENCED_BY",len(counts))
print("ATTRIBUTE_NAMES")
for k,v in attr_names.most_common(30): print(v,"\t",k)
print("TOP_SEQUENCED_BY")
for k,v in counts.most_common(100): print(v,"\t",k)
print("TOP_BIOSAMPLE_OWNER")
for k,v in owners.most_common(40): print(v,"\t",k)
print("TOP_ASSEMBLY_SUBMITTER")
for k,v in submitters.most_common(40): print(v,"\t",k)
