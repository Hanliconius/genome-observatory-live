import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('resolver', Path(__file__).resolve().parents[1]/'scripts/resolve_goat_provenance.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def row(**kwargs):
    result = dict(accession='GCA_1.1', bioproject='PRJNA1', submitter='SC', bucket='unresolved',
        programme_labels=[], production_labels=[], programme_evidence=[], research_submitter=False,
        institution_types=[], parent_projects=[], project_species=1, novelty='unknown')
    result.update(kwargs)
    return result


class ProvenanceResolutionTests(unittest.TestCase):
    def test_direct_organisation_recovers_research_with_source(self):
        out=r.resolve_record(row(), {'PRJNA1': {'organisations':['Cornell University']}}, {}, {})
        self.assertEqual(out['bucket'], 'candidate')
        self.assertEqual(out['original_bucket'], 'unresolved')
        self.assertEqual(out['organisation_evidence'][0]['source'], 'PRJNA1')
        self.assertEqual(out['organisation_evidence'][0]['value'], 'Cornell University')
        self.assertEqual(out['novelty'], 'unknown')

    def test_size_does_not_erase_research_origin(self):
        out=r.resolve_record(row(project_species=30, submitter='Example University'), {}, {}, {})
        self.assertEqual(out['bucket'], 'research')
        self.assertEqual(r.display_bucket(out, 40), 'candidate')

    def test_transitive_parent_programme_and_cycles(self):
        projects={'PRJNA1':{'parents':['PRJNA2']},'PRJNA2':{'parents':['PRJNA3']},
                  'PRJNA3':{'parents':['PRJNA1'],'title':'Named Consortium','organisations':['Example University']}}
        out=r.resolve_record(row(), projects, {'Named':'Named Consortium'}, {})
        self.assertEqual(out['bucket'], 'programme')
        self.assertIn({'label':'Named','source':'PRJNA3','field':'linked parent BioProject metadata'}, out['programme_evidence'])
        self.assertFalse(out['research_submitter'])  # parent institution is not the direct origin
        self.assertEqual(out['parent_projects'], ['PRJNA2','PRJNA3'])

    def test_repository_does_not_establish_leadership(self):
        out=r.resolve_record(row(), {'PRJNA1':{'organisations':['EMBL-EBI']}}, {}, {})
        self.assertEqual(out['bucket'], 'repository')
        self.assertFalse(out['research_submitter'])

    def test_alias_evidence_and_ambiguous_names(self):
        for alias in ['KAUST','MPIPZ','disafa_plant_genetics']:
            out=r.resolve_record(row(submitter=alias), {}, {}, {})
            self.assertEqual(out['bucket'], 'candidate')
            self.assertTrue(any(e.get('alias_url') for e in out['organisation_evidence']))
        self.assertEqual(r.resolve_record(row(submitter='BSC'), {}, {}, {})['bucket'], 'unresolved')

    def test_public_commercial_and_production_roles(self):
        self.assertEqual(r.resolve_record(row(submitter='Ministry of Health'), {}, {}, {})['bucket'],'public')
        self.assertEqual(r.resolve_record(row(submitter='Example Ltd'), {}, {}, {})['bucket'],'commercial')
        out=r.resolve_record(row(), {'PRJNA1':{'organisations':['Example Production Centre']}}, {}, {'Centre':'Example Production Centre'})
        self.assertEqual(out['bucket'],'centre')
        self.assertEqual(out['production_evidence'][0]['field'],'BioProject organisation')

    def test_idempotence_and_count_preservation(self):
        data={'records':[row(),row(accession='GCA_2.1',submitter='KAUST')]}
        first=r.resolve_payload(data,{}, {}, {});second=r.resolve_payload(first,{}, {}, {})
        self.assertEqual(first['records'],second['records'])
        self.assertEqual(len(first['records']),2)
        self.assertEqual(data['records'][1]['bucket'],'unresolved')
        self.assertEqual(second['provenance_resolution']['after_unresolved'],1)


if __name__=='__main__':unittest.main()
