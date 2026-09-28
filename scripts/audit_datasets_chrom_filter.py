#!/usr/bin/env python3
import json, subprocess, tempfile, zipfile
from pathlib import Path

ACCESSIONS=["GCA_000001405.29","GCA_000001635.9","GCA_000001215.4","GCA_000151805.2"]

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    f=td/"acc.txt"; f.write_text("\n".join(ACCESSIONS)+"\n")
    z=td/"x.zip"
    cmd=[
      "datasets","download","genome","accession","--inputfile",str(f),
      "--chromosomes","X,Y,Z,W,U,V,X1,X2,Y1,Y2,Z1,Z2,W1,W2",
      "--include","seq-report","--filename",str(z),
      "--no-progressbar","--fast-zip-validation"
    ]
    print("CMD",cmd)
    p=subprocess.run(cmd,text=True,capture_output=True)
    print("RET",p.returncode)
    print("STDERR",p.stderr[-3000:])
    if p.returncode: raise SystemExit(p.returncode)
    with zipfile.ZipFile(z) as zf:
      names=zf.namelist()
      print("FILES",names)
      for n in names:
        if n.endswith("sequence_report.jsonl"):
          print("REPORT",n)
          for line in zf.read(n).decode().splitlines():
            x=json.loads(line)
            print(x.get("assemblyAccession"),x.get("chrName"),x.get("assignedMoleculeLocationType"),x.get("role"))
