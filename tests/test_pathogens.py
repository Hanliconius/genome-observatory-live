import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_pathogens import build, binomial, origin_maps


def report(i, name, level='Chromosome'):
    return {'accession': f'GCA_9999999{i:02}.1', 'organism': {'organism_name': name, 'tax_id': i},
            'assembly_info': {'release_date': '2025-01-01', 'assembly_level': level}}


class PathogenMatching(unittest.TestCase):
    def test_aliases_strains_scope_and_exclusions(self):
        records = [report(1,'Candida glabrata CBS138'), report(2,'Nakaseomyces glabratus strain X'),
                   report(3,'Trypanosoma brucei TREU927'), report(4,'Schistosoma mansoni'),
                   report(5,'Aedes aegypti'), report(6,'Caenorhabditis elegans'),
                   report(7,'Entamoeba coli'), report(8,'Plasmodium falciparum','Scaffold')]
        d = build(records)
        self.assertEqual(d['summary']['assemblies'],5)
        self.assertEqual(d['summary']['species'],4)
        self.assertEqual(d['views']['pathogens']['summary']['assemblies'],4)
        self.assertEqual(d['views']['pathogens']['summary']['species'],3)
        self.assertFalse(any(x['role']=='Vector / surveillance' for x in d['views']['pathogens']['species_inventory']))
        fungi = d['views']['fungi']
        self.assertEqual(fungi['summary']['assemblies'],2)
        self.assertEqual(fungi['summary']['species'],1)
        self.assertEqual(d['views']['vectors']['summary']['assemblies'],1)
        self.assertEqual(d['views']['worms']['summary']['assemblies'],1)
        self.assertEqual(d['views']['protists']['summary']['assemblies'],1)
        self.assertEqual(sum(d['views'][k]['summary']['assemblies'] for k in ('vectors','protists','worms','fungi')),5)
        for view in [d]+list(d['views'].values()):
            self.assertEqual(sum(x['assemblies'] for x in view['species_inventory']),view['summary']['assemblies'])
        self.assertFalse(any(x['assemblies'] for x in d['species_inventory'] if x['species']=='Entamoeba coli'))

    def test_origin_maps_groups_and_missing_locations(self):
        rows = [dict(species_name='Schistosoma mansoni', vector_type='Parasitic flatworms', geo_loc_name='UK: London'),
                dict(species_name='Ascaris lumbricoides', vector_type='Parasitic nematodes', geo_loc_name='United Kingdom'),
                dict(species_name='Trypanosoma brucei', vector_type='Protist parasites', geo_loc_name='Pacific Ocean'),
                dict(species_name='Candida albicans', vector_type='Pathogenic fungi', geo_loc_name='not collected')]
        maps = origin_maps(rows)
        self.assertEqual(maps['all']['stats']['origin_resolved_assemblies'],3)
        self.assertEqual(maps['all']['stats']['unassigned_assemblies'],1)
        worms = maps['groups']['Parasitic worms']
        self.assertEqual(worms['countries'][0]['iso3'],'GBR')
        self.assertEqual(worms['countries'][0]['assemblies'],2)
        self.assertEqual(worms['countries'][0]['species'],2)
        self.assertEqual(maps['groups']['Protist parasites']['marine_localities'][0]['name'],'Pacific Ocean')
        self.assertEqual(sum(g['stats']['assemblies'] for g in maps['groups'].values()),4)

    def test_uncertain_names(self):
        self.assertIsNone(binomial('Plasmodium sp.'))
        self.assertIsNone(binomial('Trypanosoma cf. brucei'))
        self.assertIsNone(binomial('Schistosoma mansoni x Schistosoma haematobium'))


if __name__ == '__main__':
    unittest.main()
