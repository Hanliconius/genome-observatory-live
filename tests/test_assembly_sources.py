import copy
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from assembly_sources import merge_reports, assembly_report, enrich_biosamples
from update import reconstruct_full_history
from build_genometrics import build_sex_cache


def report(acc='GCA_000000001.1',day='2026-10-12',source='datasets',size=100):
    return dict(accession=acc,organism=dict(organism_name='Primula sinensis',tax_id=170926),
                assembly_info=dict(release_date=day,assembly_level='Chromosome'),
                assembly_stats=dict(total_sequence_length=size),
                _observatory=dict(sources=[source],metadata_pending=source!='datasets',group='Plants'))


class AssemblyInventory(unittest.TestCase):
    def test_pending_sequence_metadata_is_not_cached_as_absence_and_is_retried(self):
        cache={'GCA_000000001.1':{'tokens':['X'],'category':'Other / partial label','candidate_labels':['X']}}
        pending='GCA_000000002.1'
        with patch('build_genometrics.resolve_sex_batch',return_value={pending:{'tokens':['Z','W']}}) as resolve, patch('build_genometrics.write_json'):
            build_sex_cache(list(cache)+[pending],cache,[pending])
            resolve.assert_not_called()
            self.assertNotIn(pending,cache)
            build_sex_cache(list(cache)+[pending],cache)
            resolve.assert_called_once_with([pending])
            self.assertEqual(cache[pending]['tokens'],['Z','W'])

    def test_shared_biosample_enriches_each_assembly(self):
        rows=[report(),report('GCA_000000002.1')]
        for r in rows:r['assembly_info']['biosample']={'accession':'SAMN123'}
        xml=ET.fromstring('<BioSampleSet><BioSample accession="SAMN123"><Attributes><Attribute harmonized_name="geo_loc_name">China</Attribute></Attributes></BioSample></BioSampleSet>')
        with patch('assembly_sources.request',return_value=xml):enrich_biosamples(rows)
        self.assertTrue(all(r['_observatory']['biosample_enriched'] for r in rows))
        self.assertTrue(all(r['assembly_info']['biosample']['attributes'][0]['value']=='China' for r in rows))

    def test_same_accession_in_both_feeds_counted_once(self):
        merged,audit=merge_reports([report()],[report(source='assembly_index')])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['_observatory']['sources'],['assembly_index','datasets'])
        self.assertEqual(audit['overlapping_or_superseded_rows_removed'],1)

    def test_new_version_beats_stale_datasets_without_copying_old_statistics(self):
        merged,_=merge_reports([report(size=999)],[report('GCA_000000001.2',source='assembly_index',size=200)])
        self.assertEqual(len(merged),1)
        self.assertEqual(merged[0]['accession'],'GCA_000000001.2')
        self.assertEqual(merged[0]['assembly_stats']['total_sequence_length'],200)
        self.assertTrue(merged[0]['_observatory']['metadata_pending'])

    def test_later_enrichment_does_not_add_a_deposit(self):
        pending=report(source='assembly_index')
        before,_=merge_reports([], [pending])
        enriched=report();enriched['assembly_info']['biosample']={'accession':'SAMN123','geo_loc_name':'China'}
        after,_=merge_reports([enriched],[pending,pending])
        self.assertEqual([x['accession'] for x in before],[x['accession'] for x in after])
        self.assertFalse(after[0]['_observatory']['metadata_pending'])
        self.assertEqual(after[0]['assembly_info']['biosample']['geo_loc_name'],'China')

    def test_missing_enrichment_fields_do_not_erase_existing_same_version_metadata(self):
        pending=report(source='assembly_index')
        pending['assembly_info']['biosample']={'accession':'SAMN123','attributes':[{'name':'geo_loc_name','value':'China'}]}
        enriched=report();enriched['assembly_info']['biosample']={'accession':'SAMN123','attributes':[]}
        merged,_=merge_reports([enriched],[pending])
        self.assertEqual(merged[0]['assembly_info']['biosample']['attributes'][0]['value'],'China')

    def test_full_rebuild_retires_version_from_old_historical_day(self):
        old=dict(summary={'all':{'assemblies':1}},daily=[dict(date='2020-01-01',assemblies=1)],recent_assemblies=[])
        rows,_=merge_reports([report(day='2020-01-01')],[report('GCA_000000001.2',source='assembly_index')])
        count,daily,first=reconstruct_full_history(rows,old,'2025-01-01')
        self.assertEqual(count,1)
        self.assertEqual(sum(x['assemblies'] for x in daily),1)
        self.assertEqual([x['date'] for x in daily],['2026-10-12'])
        self.assertEqual(first,{'Primula sinensis':'2026-10-12'})

    def test_duplicate_versions_cannot_bypass_full_rebuild_guard(self):
        with self.assertRaises(RuntimeError):
            reconstruct_full_history([report(),report('GCA_000000001.2')],{},'2025-01-01')

    def test_refseq_withdrawn_and_lower_levels_do_not_enter_union(self):
        r=report();r['assembly_info']['assembly_status']='suppressed'
        low=report('GCA_000000002.1');low['assembly_info']['assembly_level']='Scaffold'
        merged,_=merge_reports([r,low],[])
        self.assertEqual(merged,[])
        with self.assertRaises(ValueError):merge_reports([report('GCF_000000001.1')],[])

    def test_assembly_dates_and_statistics_keep_their_meanings(self):
        row=dict(uid='1',assemblyaccession='GCA_000000001.1',synonym={},propertylist=['latest_genbank'],
                 assemblystatus='Chromosome',assemblyname='test',taxid='170926',
                 seqreleasedate='2026/10/12 00:00',asmreleasedate_genbank='2026/10/13 00:00',
                 meta='<Stats><Stat category="total_length" sequence_tag="all">100</Stat></Stats>')
        r=assembly_report(row,dict(name='Primula sinensis',group='Plants',eukaryote=True))
        self.assertEqual(r['assembly_info']['release_date'],'2026-10-12')
        self.assertEqual(r['_observatory']['assembly_publication_date'],'2026-10-13')
        self.assertEqual(r['assembly_stats']['total_sequence_length'],100)
        self.assertIsNone(assembly_report(dict(row,propertylist=[]),dict(name='x',group='Plants',eukaryote=True)))
        self.assertIsNone(assembly_report(row,dict(name='x',group='Other',eukaryote=False)))


if __name__=='__main__':unittest.main()
