#!/usr/bin/env python3
import json, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

BASE="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
UA="GenomeObservatoryLive/0.3 (public research dashboard; contact via repository)"

def get_json(endpoint, params, post=False):
    data=urllib.parse.urlencode(params).encode()
    if post:
        req=urllib.request.Request(BASE+endpoint,data=data,headers={"User-Agent":UA})
    else:
        req=urllib.request.Request(BASE+endpoint+"?"+data.decode(),headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode())

def post_xml(endpoint, params):
    data=urllib.parse.urlencode(params).encode()
    req=urllib.request.Request(BASE+endpoint,data=data,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=120) as r:
        return ET.fromstring(r.read())

def search_ids(token):
    term=f'Eukaryota[Organism] AND "chromosome {token}"[Title]'
    d=get_json("esearch.fcgi",{"db":"nuccore","term":term,"retmode":"json","retmax":"100000"})
    return (d.get("esearchresult") or {}).get("idlist") or []

def linked_assembly_ids(nuc_ids):
    out=set()
    for i in range(0,len(nuc_ids),400):
        chunk=nuc_ids[i:i+400]
        root=post_xml("elink.fcgi",{"dbfrom":"nuccore","db":"assembly","id":",".join(chunk)})
        for db in root.findall(".//LinkSetDb"):
            name=(db.findtext("LinkName") or "").casefold()
            if "assembly" not in name: continue
            for node in db.findall("./Link/Id"):
                if node.text: out.add(node.text)
        time.sleep(.34)
    return sorted(out)

def assembly_accessions(ids):
    out=set(); sample=None
    for i in range(0,len(ids),400):
        chunk=ids[i:i+400]
        d=get_json("esummary.fcgi",{"db":"assembly","id":",".join(chunk),"retmode":"json"},post=True)
        result=d.get("result") or {}
        for uid in result.get("uids",[]) or []:
            x=result.get(str(uid)) or {}
            if sample is None:sample=x
            for key in ("assemblyaccession","assemblyaccn","assembly_accession"):
                if x.get(key):
                    out.add(str(x[key]).strip());break
        time.sleep(.34)
    return out,sample

for token in ("X","Y","Z","W"):
    ids=search_ids(token)
    print("TOKEN",token,"NUCCORE",len(ids))
    aids=linked_assembly_ids(ids)
    print("TOKEN",token,"ASSEMBLY_IDS",len(aids))
    acc,sample=assembly_accessions(aids)
    print("TOKEN",token,"ACCESSIONS",len(acc))
    print("SAMPLE",json.dumps(sample,ensure_ascii=False)[:1500])
    print("FIRST",sorted(acc)[:20])
