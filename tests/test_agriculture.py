import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_agriculture import build, taxon_key
from import_agriculture_sources import reconcile, category, taxonomy
import csv
import hashlib
import json
import tempfile


def item(species,section,group,aliases=''):
    return dict(species=species,section=section,group=group,disease='Agricultural role',source_url='https://www.fao.org/',aliases=aliases,notes='')


def report(i,name,level='Chromosome',location='UK: London'):
    return {'accession':f'GCA_9999999{i:02}.1','organism':{'organism_name':name,'tax_id':i},
            'assembly_info':{'release_date':'2025-01-01','assembly_level':level,'biosample':{'geo_loc_name':location}}}


class AgricultureMatching(unittest.TestCase):
    def test_three_roles_aliases_hybrids_groups_and_origins(self):
        catalogue=[item('Oryza sativa','organisms','Cereals'),item('Fragaria x ananassa','organisms','Fruit & nuts','Fragaria ananassa'),
                   item('Spodoptera frugiperda','pests','Insect pests'),item('Pyricularia oryzae','pathogens','Fungal plant pathogens','Magnaporthe oryzae')]
        reports=[report(1,'Oryza sativa Japonica Group'),report(2,'Oryza sativa cultivar X'),report(3,'Fragaria x ananassa cultivar Y'),
                 report(4,'Spodoptera frugiperda'),report(5,'Magnaporthe oryzae strain 70-15'),report(6,'Oryza rufipogon'),
                 report(7,'Oryza sativa','Scaffold'),report(8,'Fragaria vesca'),report(9,'Oryza sativa x Oryza rufipogon')]
        d=build(reports,catalogue)
        self.assertEqual(d['views']['organisms']['summary']['assemblies'],3)
        self.assertEqual(d['views']['organisms']['summary']['species'],2)
        self.assertEqual(d['views']['pests']['summary']['assemblies'],1)
        self.assertEqual(d['views']['pathogens']['summary']['assemblies'],1)
        cereals=d['views']['organisms']['groups']['Cereals']
        self.assertEqual(cereals['summary']['assemblies'],2)
        self.assertEqual(cereals['source']['species_names'],1)
        self.assertEqual(cereals['origin_maps']['all']['countries'][0]['assemblies'],2)
        for view in d['views'].values():
            self.assertEqual(sum(x['summary']['assemblies'] for x in view['groups'].values()),view['summary']['assemblies'])
            self.assertEqual(sum(x['assemblies'] for x in view['species_inventory']),view['summary']['assemblies'])

    def test_ambiguous_names_and_aliases(self):
        self.assertEqual(taxon_key('Fragaria × ananassa cultivar X'),'fragaria x ananassa')
        self.assertEqual(taxon_key('Fragaria x ananassa x Fragaria vesca'),'')
        self.assertEqual(taxon_key('Oryza cf. sativa'),'')
        with self.assertRaises(ValueError):
            build([], [item('Oryza sativa','organisms','Cereals'),item('Oryza glaberrima','organisms','Cereals','Oryza sativa')])


class AgricultureProvenance(unittest.TestCase):
    def test_overlapping_sources_retained_without_duplicate_taxa_or_assemblies(self):
        name='Diorhabda carinulata'
        evidence=dict(species=name,tax_id='101061',lineage='Eukaryota; Arthropoda',eukaryote=True)
        def candidate(source,original=name,host=''):
            return dict(source_id=source,original_name=original,tax_id='',section='pests',group='Insect pests',
                        disease='Project target',host_or_commodity=host,evidence_url='https://example.org/'+source,
                        reference_urls='https://pubmed.ncbi.nlm.nih.gov/1/',basis='Species listed')
        override={name:dict(section='organisms',group='Biological control',role='Tamarisk control',
                            evidence_url='https://www.ars.usda.gov/',notes='Documented control agent')}
        rejected=[]
        cat,members=reconcile([], [candidate('ag100_targets'),candidate('ag100_targets'),candidate('phibase_5_6',host='Tamarix')],
                              {},{taxon_key(name):{'101061':evidence}},override,rejected)
        self.assertEqual(len(cat),1)
        self.assertEqual(cat[0]['section'],'organisms')
        self.assertEqual({m['source_id'] for m in members},{'ag100_targets','phibase_5_6','role_review'})
        self.assertTrue(all(m['assigned_role']=='organisms' for m in members))
        self.assertFalse(rejected)
        d=build([report(1,name),report(1,name)],cat)
        self.assertEqual(d['views']['organisms']['summary']['assemblies'],1)
        self.assertEqual(d['views']['pests']['summary']['assemblies'],0)

    def test_unresolved_or_non_eukaryotic_labels_do_not_enter_catalogue(self):
        c=dict(source_id='caps_2026',original_name='Escherichia coli',tax_id='',section='',group='',
               disease='',host_or_commodity='',evidence_url='',reference_urls='',basis='Species listed')
        rejected=[]
        cat,members=reconcile([], [c,dict(c,original_name='Unknown species')],{},
                              {'escherichia coli':{'562':dict(species='Escherichia coli',tax_id='562',lineage='Bacteria',eukaryote=False)}},
                              {},rejected)
        self.assertFalse(cat);self.assertFalse(members);self.assertEqual(len(rejected),2)


class CountryAgricultureSources(unittest.TestCase):
    def test_reviewed_australian_roles_and_scientific_matching_names(self):
        path=Path(__file__).resolve().parents[1]/'data/status/agriculture_country_candidates.tsv'
        with path.open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        rows=[x for x in rows if x['source_id']=='au_bioplatforms_ipm']
        indexed={x['match_name']:x for x in rows if x['group']!='excluded'}
        self.assertEqual(indexed['Phaulacridium vittatum']['section'],'pests')
        self.assertEqual(indexed['Pezothrips kellyanus']['section'],'pests')
        self.assertEqual(indexed['Austroplebeia australis']['group'],'Pollinators')
        self.assertEqual(indexed['Spalangia endius']['group'],'Biological control')
        self.assertNotIn('Wingless grasshopper',indexed)
        self.assertTrue(any(x['group']=='excluded' and 'Dongara weevil' in x['original_name'] for x in rows))

    def test_national_plant_lists_use_lineage_for_broad_groups(self):
        x=dict(source_id='jp_maff_quarantine',section='',group='plant')
        for lineage,expected in [('Eukaryota; Arthropoda; Acari',('pests','Mite pests')),
                                 ('Eukaryota; Mollusca',('pests','Mollusc pests')),
                                 ('Eukaryota; Fungi',('pathogens','Fungal plant pathogens')),
                                 ('Eukaryota; Oomycetes',('pathogens','Oomycete plant pathogens'))]:
            self.assertEqual(category(x,dict(lineage=lineage)),expected)


class TaxonomyResolution(unittest.TestCase):
    def test_current_canonical_name_wins_over_truncated_historical_synonym(self):
        xml="""<TaxaSet>
        <Taxon><TaxId>1</TaxId><ScientificName>Anoplophora chinensis</ScientificName><Rank>species</Rank><Lineage>Eukaryota; Arthropoda</Lineage></Taxon>
        <Taxon><TaxId>2</TaxId><ScientificName>Anoplophora malasiaca</ScientificName><Rank>species</Rank><Lineage>Eukaryota; Arthropoda</Lineage><OtherNames><Synonym>Anoplophora chinensis malasiaca</Synonym></OtherNames></Taxon>
        <Taxon><TaxId>3</TaxId><ScientificName>Anoplophora</ScientificName><Rank>genus</Rank><Lineage>Eukaryota; Arthropoda</Lineage></Taxon>
        </TaxaSet>"""
        signature=hashlib.sha256(json.dumps([[],[]]).encode()).hexdigest()[:12]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/('ag_taxonomy_'+signature+'.xml');path.write_text(xml)
            by_id,by_name,_=taxonomy(Path(tmp),[])
            self.assertEqual(set(by_name['anoplophora chinensis']),{'1'})
            self.assertNotIn('3',by_id)


if __name__ == '__main__':
    unittest.main()
