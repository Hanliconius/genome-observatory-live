import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_agriculture import build, taxon_key


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


if __name__ == '__main__':
    unittest.main()
