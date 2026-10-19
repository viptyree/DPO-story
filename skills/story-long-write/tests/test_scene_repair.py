import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scene_repair import requested_repair


class RepairTest(unittest.TestCase):
    def setup_case(self, folder):
        stem = folder / 'scene_01'
        text = '前段事实保持不变。' * 25 + '\n\n你把遗体带回家吧。'
        stem.with_suffix('.md').write_text(text+'\n',encoding='utf-8',newline='\n')
        meta = {'model':'local', 'finish_reason':'stop', 'draft_sha256':hashlib.sha256(stem.with_suffix('.md').read_bytes()).hexdigest()}
        doc = {'system':'只输出正文','user':'〖人物状态〗\n甲\n〖前情〗\n遗体须暂留\n〖事件骨架〗\n1. 核验\n〖写作要求〗\n保持事实',
               'model':'local','adapters':[{'id':0,'scale':.2}],'sampling':{'temperature':.35}}
        review = {'schema_version':1,'status':'repair','request_sha256':'request','draft_sha256':meta['draft_sha256'],
                  'repairs':[{'before':'你把遗体带回家吧。','instruction':'遗体与家属都留在原处等待核验，不得带走。'}]}
        stem.with_suffix('.review.json').write_text(json.dumps(review),encoding='utf-8')
        return stem, text, meta, doc, review

    def test_local_model_supplies_replacement_preserves_source_and_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            stem, text, meta, doc, review = self.setup_case(Path(directory))
            original = stem.with_suffix('.md').read_bytes()
            calls = []
            def request(*args, **kwargs):
                calls.append(args[3])
                return '你留在这里，等我核验。', 'stop', 'local'
            def write(path, content):
                path.write_text(content,encoding='utf-8',newline='\n')
            result = requested_repair(stem,text,meta,doc,'request',request,write,'http://local')
            self.assertEqual(result[1], text.replace('你把遗体带回家吧。','你留在这里，等我核验。'))
            self.assertEqual(stem.with_suffix('.md').read_bytes(), original)
            self.assertEqual(result[2]['errors'], [])
            self.assertNotIn('你把遗体带回家吧。', calls[0])
            requested_repair(stem,text,meta,doc,'request',request,write,'http://local')
            self.assertEqual(len(calls), 1)
            review['repairs'][0]['instruction'] = '更换修订要求'
            stem.with_suffix('.review.json').write_text(json.dumps(review),encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '已变化'):
                requested_repair(stem,text,meta,doc,'request',request,write,'http://local')

    def test_controller_cannot_supply_replacement_text(self):
        with tempfile.TemporaryDirectory() as directory:
            stem,text,meta,doc,review = self.setup_case(Path(directory))
            review['repairs'][0]['after'] = '主控写的新正文'
            stem.with_suffix('.review.json').write_text(json.dumps(review),encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '不能提供替换正文'):
                requested_repair(stem,text,meta,doc,'request',None,None,'http://local')

    def test_empty_response_cannot_delete_a_paragraph(self):
        with tempfile.TemporaryDirectory() as directory:
            stem,text,meta,doc,_ = self.setup_case(Path(directory))
            def write(path, content):
                path.write_text(content,encoding='utf-8',newline='\n')
            result = requested_repair(stem,text,meta,doc,'request',lambda *a,**k: ('','stop','local'),write,'http://local')
            self.assertTrue(result[2]['errors'])

    def test_nonunique_span_and_stale_review_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            stem,text,meta,doc,review = self.setup_case(Path(directory))
            review['repairs'][0]['before'] = '前段事实保持不变。'
            stem.with_suffix('.review.json').write_text(json.dumps(review),encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '唯一出现'):
                requested_repair(stem,text,meta,doc,'request',None,None,'http://local')
            review['draft_sha256'] = 'stale'
            stem.with_suffix('.review.json').write_text(json.dumps(review),encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '指纹不符'):
                requested_repair(stem,text,meta,doc,'request',None,None,'http://local')


if __name__ == '__main__':
    unittest.main()
