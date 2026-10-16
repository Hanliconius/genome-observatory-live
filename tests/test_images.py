import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import update


def assembly(name,day,acc):
    return dict(organism_name=name,release_date=day,accession=acc,genus=name.split()[0],family='Testaceae')


class ImageSelection(unittest.TestCase):
    def setUp(self):
        update._IMAGE_LOOKUPS.clear()
        update._WIKI_DISABLED.clear()

    def test_failed_recheck_keeps_newer_species_cached_image(self):
        new=assembly('Primula sinensis','2026-10-13','GCA_2.1')
        old=assembly('Sus scrofa','2026-10-06','GCA_1.1')
        image={'thumb_url':'https://example.org/primula.jpg','matched_name':'Primula sinensis'}
        with patch('update.commons_image',return_value=None):
            selected=update.select_featured_assembly([old,new],{'Primula sinensis':image},{})
        self.assertIs(selected,new)
        self.assertEqual(new['image'],image)

    def test_newer_fresh_image_beats_old_cached_image(self):
        new=assembly('Primula sinensis','2026-10-13','GCA_2.1')
        old=assembly('Sus scrofa','2026-10-06','GCA_1.1')
        with patch('update.commons_image',return_value={'thumb_url':'https://example.org/new.jpg'}):
            self.assertIs(update.select_featured_assembly([old,new],{'Sus scrofa':{'thumb_url':'old'}},{}),new)

    def test_repeated_candidates_share_one_lookup_per_name(self):
        with patch('update.wikidata_image',return_value=None) as wd,patch('update.commons_search',return_value=None),patch('update.time.sleep'):
            update.commons_image(['Primula sinensis','Primula'])
            update.commons_image(['Primula sinensis','Primula'])
        self.assertEqual(wd.call_count,2)

    def test_transient_timeout_retries_without_erasing_success(self):
        response=Mock();response.json.return_value={'query':{'pages':{}}}
        with patch.object(update.S,'get',side_effect=[requests.Timeout('temporary'),response]) as get,patch('update.time.sleep'):
            self.assertEqual(update.wiki_json('test-api',{}),response.json.return_value)
        self.assertEqual(get.call_count,2)
        self.assertNotIn('test-api',update._WIKI_DISABLED)

    def test_wikidata_ignores_an_unrelated_entity_with_an_image(self):
        entities={'search':[{'id':'Q1'}]}
        unrelated={'entities':{'Q1':{'claims':{'P18':[{'mainsnak':{'datavalue':{'value':'logo.jpg'}}}]}}}}
        with patch('update.wiki_json',side_effect=[entities,unrelated]),patch('update.commons_file_info') as image:
            self.assertIsNone(update.wikidata_image('Primula sinensis'))
        image.assert_not_called()


if __name__=='__main__':unittest.main()
