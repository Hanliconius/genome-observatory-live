#!/usr/bin/env python3
"""Extract reviewed national source snapshots into auditable candidate TSVs.

Inputs are downloaded official HTML/PDF/Word snapshots; PDF text is produced
with pdftotext -layout, Word text with antiword. This is an explicit review
operation, never part of daily genome counting.
"""
import argparse
import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup
from import_agriculture_sources import write_tsv, TODAY, STATUS

SOURCE_FIELDS = ['source_id','name','url','version','retrieved_at','scope','license','sha256','country']
CANDIDATE_FIELDS = ['source_id','original_name','match_name','section','group','disease','host_or_commodity','evidence_url','reference_urls','tax_id','basis']


def extract(cache):
    sources, rows = [], []
    def source(sid,name,country,url,version,scope,filename):
        raw=(cache/filename).read_bytes()
        sources.append(dict(source_id=sid,name=name,country=country,url=url,version=version,retrieved_at=TODAY,
                            scope=scope,license='',sha256=hashlib.sha256(raw).hexdigest()))
        return raw
    def add(sid,label,match='',section='',group='plant',role='',host='',url='',basis=''):
        s=next(x for x in sources if x['source_id']==sid)
        rows.append(dict(source_id=sid,original_name=label,match_name=match or label,section=section,group=group,
                         disease=role or s['name']+' listed organism',host_or_commodity=host,evidence_url=url or s['url'],
                         reference_urls='',basis=s['country']+' — '+basis,tax_id=''))
    def soup(raw):return BeautifulSoup(raw,'html.parser')

    sid='br_mapa_absent'
    source(sid,'Brazil MAPA absent quarantine pests','Brazil',
           'https://www.gov.br/agricultura/pt-br/assuntos/sanidade-animal-e-vegetal/sanidade-vegetal/PORTARIASDA_MAPAN1.679DE31DEAGOSTODE2026.pdf',
           'Portaria 1.679, 2026-08-31; corrected publication 2026-09-04',
           'Official absent quarantine pests; plants, forestry and agricultural trade. Listing does not mean occurrence in Brazil. Genus-only entries are excluded.', 'br_absent_pdf.pdf')
    text=(cache/'br_absent.txt').read_text().split('ANEXO',1)[1].split('Republicada por',1)[0]
    for line in text.splitlines():
        label=line.strip()
        if re.match(r'^[A-Z][a-z]+ (?:[a-z]|spp\.)',label):
            add(sid,label,basis='Absent quarantine pest; original synonyms and qualifiers retained')

    sid='br_mapa_present'
    raw=source(sid,'Brazil MAPA present quarantine pests','Brazil',
               'https://www.gov.br/agricultura/pt-br/assuntos/defesa-agropecuaria/vegetal/protecao-de-plantas-1/pragas-quarentenarias-presentes-2013-pqp',
               'Page updated 2026-08-13', 'Official present quarantine pests under control; selected regulated taxa, not all Brazilian agricultural pests.', 'br_present.html')
    core=soup(raw).select_one('#content-core')
    for p in core.find_all('p'):
        label=p.get_text(' ',strip=True)
        for name in re.findall(r'\(([A-Z][a-z]+ [a-z][a-z-]+[^)]*)\)',label):
            add(sid,name,role=label.split('(')[0].strip(),basis='Present quarantine pest under official control')

    sid='cn_mara_domestic'
    source(sid,'China MARA agricultural quarantine list','China',
           'https://www.moa.gov.cn/govpublic/ZZYGLS/202409/P020240903392697239636.pdf',
           '2024 published species list', 'National agricultural quarantine list, including insects, nematodes, pathogens and weeds. Genus-only and non-eukaryotic entries excluded.', 'cn_domestic_pdf.pdf')
    for m in re.finditer(r'^\s*\d+\.\s*(.*)',(cache/'cn_domestic.txt').read_text(),re.M):
        label=m.group(1)
        names=re.findall(r'[A-Z][a-z]+ (?:[a-z][a-z-]+|spp\.)(?:[^\n]*)',label)
        if names:add(sid,names[0],basis='National agricultural quarantine organism; species roll-up')

    sid='cn_import_quarantine'
    source(sid,'China import quarantine catalogue','China',
           'https://assets.ippc.int/static/media/files/reportingobligation/2025/01/07/CATALOGUE_OF_QUARANTINE_PESTS_FOR_IMPORT_PLANTS_TO_THE_PEOPLES_REPUBLIC_OF_CHINA_updated_20241128.doc',
           '2024-11-28 catalogue; reported to IPPC 2025-01-07',
           'Official import quarantine catalogue: 493 species/genera across source categories; explicit eukaryotic species only. Non-Chinese and strain restrictions remain source qualifiers.', 'cn_import_doc.doc')
    for line in (cache/'cn_import.txt').read_text().splitlines():
        cells=line.split('|')
        if len(cells)>=4:
            label=cells[2].strip()
            if re.match(r'^[A-Z][a-z]+(?: |$)',label):add(sid,label,basis='Import quarantine organism; original restrictions retained')

    sid='ca_cfia_regulated'
    raw=source(sid,'Canada CFIA regulated pests','Canada',
               'https://inspection.canada.ca/en/plant-health/invasive-pests-and-plants/regulated-pests',
               'Public list snapshot '+TODAY,
               'Official plant protection list: agricultural, horticultural and forest pests/pathogens. Restrictions may apply to specific races or source regions.', 'ca_regulated.html')
    for tr in soup(raw).select('table tr'):
        c=tr.find_all('td')
        if len(c)<3:continue
        typ=c[2].get_text(' ',strip=True)
        groups={'Insect':'Insect pests','Mite':'Mite pests','Mollusc':'Mollusc pests','Nematode':'Nematode pests','Plant':'Weeds','Fungus':'plant'}
        label=c[0].get_text(' ',strip=True)
        if typ in groups:
            names=[label]
            # Expand only explicitly enumerated abbreviated species in a genus entry.
            genus=re.match(r'^([A-Z][a-z]+) spp\.',label)
            if genus:
                names=[genus.group(1)+' '+m for m in re.findall(r'\b'+genus.group(1)[0]+r'\. ([a-z][a-z-]+)',label)] or [label]
            for n in names:add(sid,n,section='pests' if typ!='Fungus' else '',group=groups[typ],role=c[1].get_text(' ',strip=True),basis='Regulated plant-health organism; source restrictions retained')
        else:add(sid,label,role=typ,basis='Non-eukaryotic source category; taxonomy/scope exclusion')

    sid='jp_maff_quarantine'
    raw=source(sid,'Japan MAFF quarantine pests','Japan',
               'https://www.maff.go.jp/pps/j/law/houki/shorei/E_Annexed_Table1.html',
               'Current table last updated 2026-06-18',
               'Current official quarantine table (not the future table effective December 2026): arthropods, nematodes, molluscs and fungi. Unknown-agent diseases, bacteria and viruses are excluded.', 'jp_quarantine.html')
    for tr in soup(raw).select('tr'):
        c=tr.find_all('td')
        if len(c)!=2:continue
        heading=c[0].get_text(' ',strip=True)
        if not any(k in heading for k in ['Arthropods','Nematodes','Mollusks','Fungi']):continue
        group='plant' if 'Fungi' in heading else 'Nematode pests' if 'Nematodes' in heading else 'Mollusc pests' if 'Mollusks' in heading else 'plant'
        for name in c[1].get_text(' ',strip=True).split(','):
            if name.strip():add(sid,name.strip(),section='pests' if group!='plant' else '',group=group,basis='Quarantine table '+heading)

    sid='gh_nppo_quarantine'
    source(sid,'Ghana NPPO quarantine list','Ghana',
           'https://assets.ippc.int/static/media/files/reportingobligation/2020/12/04/GHANA-_QUARANTINE_PEST_LIST_IPPC_doc.pdf',
           'October 2017 content; IPPC attachment 2020-12-04, report republished 2026-07-16',
           'Historical NPPO crop-specific quarantine insects/mites, diseases and nematodes. Preserved as a dated source, not a claim of current legal status. Source presence flags do not represent genome sample origins.', 'gh_pests_pdf.pdf')
    section='insects'
    for line in (cache/'gh_pests.txt').read_text().splitlines():
        if 'QUARANTINE DISEASES' in line:section='diseases'
        if 'QUARANTINE NEMATODES' in line:section='nematodes'
        # In this document the Crop column is left of x=17; organisms are x=17..60.
        cell=re.split(r'\s{2,}',line[17:60].strip())[0]
        m=re.match(r'^([A-Z][a-z]+)(?: \([A-Z][a-z]+\))? ([a-z][a-z-]+)',cell)
        if not m:continue
        match=m.group(1)+' '+m.group(2)
        add(sid,cell,match=match,group='plant',basis='Dated NPPO crop pest table; '+section+'; exact organism column extracted')

    sid='au_daff_priority'
    # Reviewed transcription of the current official webpage's scientific-name column.
    # The source webpage timed out for direct download; this extract came from its web retrieval.
    raw=source(sid,'Australia DAFF priority plant pests','Australia',
               'https://www.agriculture.gov.au/biosecurity-trade/pests-diseases-weeds/plant/national-priority-plant-pests',
               '2024 list endorsed 2024-12-02',
               'National priority plant pests/diseases and vectors; includes exotic species/strains. Hash is of the reviewed scientific-name transcription, not original HTML. Genus-only/non-eukaryotic entries excluded.', 'au_priority_reviewed.txt')
    for label in raw.decode().splitlines():
        if label.strip():add(sid,label.strip(),basis='National priority plant pest; source exotic/strain qualifier retained')

    sid='au_bioplatforms_ipm'
    raw=source(sid,'Australia Bioplatforms IPM','Australia',
               'https://bioplatforms.com/project/integrated-pest-management-omics-initiative/',
               'Project table snapshot '+TODAY,
               'Reviewed agricultural pest, pollinator and biocontrol projects from national IPM programme. A sequencing target is not evidence of an already released qualifying assembly. Non-agricultural/unidentified projects excluded.', 'au_ipm.html')
    project_rows=soup(raw).select('table tr')[1:]
    if len(project_rows)!=42:
        raise ValueError('Australian IPM project table changed; review roles before importing')
    # Explicit reviewed identities correct split formatting, subgenus labels and source typos.
    pollinators={0:'Lasioglossum dotatum',1:'Austroplebeia australis',2:'Amegilla pulchra',3:'Exoneura angophorae',4:'Lipotriches australica',10:'Exoneura robusta'}
    controls={5:['Diachasmimorpha kraussii'],6:['Diachasmimorpha kraussii','Diachasmimorpha tryoni','Fopius arisanus'],8:['Spalangia endius','Muscidifurax raptor'],33:['Dipterophagus daci'],34:['Anaphes nitens'],35:['Avetianella longoi']}
    pests={7:'Phaulacridium vittatum',13:'Rhopalosiphum padi',14:'Pezothrips kellyanus',15:'Agrotis munda',16:'Agrotis ipsilon',18:'Gonipterus platensis',20:'Amblypelta nitida',21:'Amblypelta lutescens lutescens',23:'Theba pisana',24:'Dohrniphora trigonae',25:'Nysius vinitor',26:'Sidnia kinbergi',27:'Diachus auratus',28:'Dindymus versicolor',29:'Caliroa cerasi',30:'Phoracantha mastersi',31:'Scirtothrips dorsalis',32:'Liriomyza trifolii',36:'Parthenolecanium corni',40:'Rhipicephalus australis',41:'Haematobia irritans exigua'}
    excluded={9,11,12,17,19,22,37,38,39}
    for i,tr in enumerate(project_rows):
        c=tr.find_all('td')
        if len(c)<2:continue
        original=c[0].get_text(' ',strip=True);description=c[1].get_text(' ',strip=True)
        if i in excluded:
            add(sid,original,match='',group='excluded',basis='Review exclusion: unidentified taxon or no explicit agricultural role in project description');continue
        if i in pollinators:names=[pollinators[i]];role='Crop pollinator';sec='organisms';group='Pollinators'
        elif i in controls:names=controls[i];role='Agricultural biological control';sec='organisms';group='Biological control'
        else:
            names=[pests[i]]
            role='Agricultural pest';sec='pests';group='Livestock arthropod pests' if i in (40,41) else 'Mollusc pests' if i==23 else 'Insect pests'
        for name in names:
            add(sid,original,match=name,section=sec,group=group,role=role,host=description,
                basis='Reviewed primary agricultural role; explicit names expanded only where project context identifies genus/species')
    unique={(r['source_id'],r['original_name'],r['match_name'],r['section']):r for r in rows}
    return sources,list(unique.values())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache-dir',type=Path,required=True);a=p.parse_args()
    sources,rows=extract(a.cache_dir)
    write_tsv(STATUS/'agriculture_country_sources.tsv',sources,SOURCE_FIELDS)
    write_tsv(STATUS/'agriculture_country_candidates.tsv',rows,CANDIDATE_FIELDS)
    print('Country snapshots:',len(sources),'sources;',len(rows),'reviewable labels')
