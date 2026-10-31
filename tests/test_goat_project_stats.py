import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('project_stats', Path(__file__).resolve().parents[1]/'scripts/build_goat_project_stats.py')
stats = importlib.util.module_from_spec(spec); spec.loader.exec_module(stats)

def report(acc='GCA_000000001.1', taxid=1, day='2024-01-01', project='PRJNA1', sub='Example University', lineage=None):
    return {'accession': acc, 'organism': {'tax_id': taxid, 'organism_name': 'Example species'},
            'assembly_info': {'release_date': day, 'submitter': sub, 'bioproject_accession': project,
                              'bioproject_lineage': lineage or []}}

class ProjectStatsTests(unittest.TestCase):
    def run_rows(self, rows, history=None, projects=None):
        taxonomy = {'1': {'species_id':'100', 'species_name':'Example species', 'group':'Animals'},
                    '2': {'species_id':'100', 'species_name':'Example species', 'group':'Animals'},
                    '3': {'species_id':'300', 'species_name':'Another species', 'group':'Plants'}}
        with tempfile.TemporaryDirectory() as temp, patch.object(stats, 'ROOT', Path(temp)), patch.object(stats, 'read_gz', return_value=history or {}):
            return stats.assemble(rows, projects or {}, taxonomy)

    def test_version_and_refseq_do_not_add_counts(self):
        rows=self.run_rows([report('GCA_000000001.1'), report('GCA_000000001.2'), report('GCF_000000001.2')])
        self.assertEqual([r['accession'] for r in rows], ['GCA_000000001.2'])

    def test_species_mapping_collapses_subspecies_and_same_day_ties(self):
        rows=self.run_rows([report(taxid=1),report('GCA_000000002.1',taxid=2)])
        self.assertEqual(sum(r['first'] for r in rows),1)
        self.assertEqual(sum(r['first_day'] for r in rows),2)
        self.assertEqual(rows[0]['project_species'],1)

    def test_explicit_parent_programme_retained_with_other_signals(self):
        lineage=[{'bioprojects':[{'accession':'PRJNA99','title':'Darwin Tree of Life'}]}]
        row=self.run_rows([report(lineage=lineage)])[0]
        self.assertEqual(row['bucket'],'programme')
        self.assertTrue(row['university_submitter'])
        self.assertEqual(row['programme_evidence'][0]['source'],'PRJNA99')

    def test_missing_metadata_is_not_small_team(self):
        row=self.run_rows([report(sub='',project='')])[0]
        self.assertEqual(row['bucket'],'unresolved')
        self.assertEqual(row['novelty'],'unknown')
        self.assertFalse(row['project_metadata'])

    def test_historical_scaffold_upgrade_and_same_stem_revision(self):
        old={'date':'2010-01-01','accession':'GCA_000000001.1','level':'Scaffold'}
        history={'species':{'100':{'first':old,'first_lower':old,'first_high':None}},'lower_by_stem':{'GCA_000000001':old}}
        row=self.run_rows([report('GCA_000000001.2')],history)[0]
        self.assertEqual(row['novelty'],'upgrade')
        self.assertTrue(row['same_stem_upgrade'])

    def test_historical_chromosome_prevents_false_first_upgrade(self):
        old={'date':'2010-01-01','accession':'GCA_000000009.1','level':'Scaffold'}
        high={'date':'2015-01-01','accession':'GCA_000000009.2','level':'Chromosome'}
        history={'species':{'100':{'first':old,'first_lower':old,'first_high':high}}}
        self.assertEqual(self.run_rows([report()],history)[0]['novelty'],'additional')

    def test_first_ever_uses_all_level_context(self):
        old={'date':'2024-01-01','accession':'GCA_000000001.1','level':'Chromosome'}
        history={'species':{'100':{'first':old,'first_lower':None,'first_high':old}}}
        self.assertEqual(self.run_rows([report()],history)[0]['novelty'],'first_ever')

    def test_same_release_date_does_not_hide_an_earlier_scaffold_version(self):
        old={'date':'2024-01-01','accession':'GCA_000000001.1','level':'Scaffold'}
        history={'species':{'100':{'first':old,'first_lower':old,'first_high':None}},'lower_by_stem':{'GCA_000000001':old}}
        self.assertEqual(self.run_rows([report('GCA_000000001.2')],history)[0]['novelty'],'upgrade')

    def test_all_level_project_footprint_overrides_chromosome_subset(self):
        row=self.run_rows([report()],{'project_species':{'PRJNA1':80}})[0]
        self.assertEqual(row['project_species'],80)
        self.assertEqual(row['bucket'],'unresolved')

    def test_grants_use_agency_and_id(self):
        grants={'PRJNA1':{'grants':[{'agency':'Funder A','id':'123','title':''}]},
                'PRJNA2':{'grants':[{'agency':'Funder B','id':'123','title':''}]}}
        rows=self.run_rows([report(),report('GCA_000000002.1',taxid=3,project='PRJNA2')],projects=grants)
        self.assertEqual([r['grant_species_max'] for r in rows],[1,1])

if __name__ == '__main__': unittest.main()
