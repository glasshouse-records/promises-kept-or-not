"""Rank SEC N-CEN registrants by equity-like net assets and mark which are covered by config/institutions.yaml.

Usage: download data/ncen/<q>_ncen.zip (SEC Form N-CEN data sets), unzip SUBMISSION/REGISTRANT/FUND_REPORTED_INFO/ADVISER
into data/ncen/<q>/, then: python scripts/ncen_coverage.py <n_families> <out.json> <n_registrants>
"""
import csv, sys, yaml, collections
csv.field_size_limit(10**9)
D="data/ncen/"
cfg=yaml.safe_load(open("config/institutions.yaml"))["institutions"]
covered={}
for k,v in cfg.items():
    for e in v.get("npx_ciks") or []: covered[str(e["cik"]).lstrip("0")]=k
latest={}  # cik -> (date, acc, row)
for q in ["2025q4","2026q1","2026q2","2026q3"]:
    sub={r["ACCESSION_NUMBER"]:r for r in csv.DictReader(open(D+q+"/SUBMISSION.tsv"),delimiter="\t")}
    for r in csv.DictReader(open(D+q+"/REGISTRANT.tsv"),delimiter="\t"):
        s=sub.get(r["ACCESSION_NUMBER"]); 
        if not s: continue
        cik=r["CIK"].lstrip("0"); per=s["REPORT_ENDING_PERIOD"]
        from datetime import datetime
        d=datetime.strptime(per,"%d-%b-%Y")
        if cik not in latest or d>latest[cik][0]: latest[cik]=(d,r["ACCESSION_NUMBER"],r,q)
accs={v[1]:k for k,v in latest.items()}
assets=collections.Counter(); mmf=collections.Counter(); advisers=collections.defaultdict(collections.Counter)
for q in ["2025q4","2026q1","2026q2","2026q3"]:
    for r in csv.DictReader(open(D+q+"/FUND_REPORTED_INFO.tsv"),delimiter="\t"):
        cik=accs.get(r["ACCESSION_NUMBER"])
        if not cik: continue
        try: a=float(r["MONTHLY_AVG_NET_ASSETS"] or r["DAILY_AVG_NET_ASSETS"] or 0)
        except: a=0
        import re
        if r["IS_MONEY_MARKET"]=="Y" or r["IS_FUND_OF_FUND"]=="Y" or r["IS_TARGET_DATE"]=="Y" or re.search(r"(?i)bond|municipal|muni|fixed income|treasury|tax-exempt|tax-free|income fund|credit|govern|money market|short[- ]term|duration|mortgage|high yield|loan|ultra", r["FUND_NAME"]): mmf[cik]+=a; continue
        assets[cik]+=a
    for r in csv.DictReader(open(D+q+"/ADVISER.tsv"),delimiter="\t"):
        acc=r["FUND_ID"].split("_")[0]; cik=accs.get(acc)
        if cik and r["ADVISER_TYPE"]=="Advisor": advisers[cik][r["ADVISER_NAME"]]+=1
fam=collections.defaultdict(lambda:[0,0,[],set()])
tot=cov=0
for cik,(d,acc,r,q) in latest.items():
    if r["INVESTMENT_COMPANY_TYPE"] not in ("N-1A","N-2","N-3"): pass
    a=assets[cik]; tot+=a
    f=r["FAMILY_INVESTMENT_COMPANY_NAME"] or (advisers[cik].most_common(1)[0][0] if advisers[cik] else r["REGISTRANT_NAME"])
    if cik in covered: cov+=a; fam[f][1]+=a
    else: fam[f][0]+=a; fam[f][2].append((a,cik,r["REGISTRANT_NAME"]))
    if advisers[cik]: fam[f][3].add(advisers[cik].most_common(1)[0][0])
print(f"non-MMF assets total ${tot/1e12:.1f}T, covered ${cov/1e12:.1f}T = {cov/tot:.0%}")
rows=sorted(fam.items(),key=lambda x:-x[1][0])
cum=cov
for i,(f,(u,c,regs,adv)) in enumerate(rows[:int(sys.argv[1])]):
    cum+=u
    print(f"{i+1:3} ${u/1e9:8.0f}B uncov  ${c/1e9:7.0f}B cov  cum {cum/tot:.1%}  {f[:28]:28} n={len(regs):3} adv={'; '.join(sorted(adv))[:90]}")
print("---- top uncovered registrants")
allr=sorted(((a,c,n,f) for f,(u,cv,regs,adv) in fam.items() for a,c,n in regs),reverse=True)
import json; json.dump([(a,c,n,f) for a,c,n,f in allr],open(sys.argv[2],"w"))
for a,c,n,f in allr[:int(sys.argv[3])]: print(f"${a/1e9:7.0f}B {c:>8} {n[:60]:60} [{f[:20]}]")
