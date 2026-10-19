import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from base_scene_critic import payload,validate_verdict


class CriticTest(unittest.TestCase):
    def test_critic_disables_adapter_only_in_its_own_request(self):
        adapters=[{'id':3,'scale':.2}]
        body=payload('local',adapters,'本场核验','模型原稿',42813)
        self.assertEqual(body['lora'],[{'id':3,'scale':0.}])
        self.assertEqual(adapters,[{'id':3,'scale':.2}])
        self.assertNotIn('陆平川',str(body))

    def test_fabricated_evidence_or_inconsistent_verdict_is_unusable(self):
        validate_verdict({'status':'fail','issues':['动作重复'],'evidence':['原稿句子']},'原稿句子。')
        with self.assertRaisesRegex(ValueError,'引文'):
            validate_verdict({'status':'fail','issues':['问题'],'evidence':['虚构句子']},'原稿句子。')
        with self.assertRaisesRegex(ValueError,'矛盾'):
            validate_verdict({'status':'pass','issues':['仍有问题'],'evidence':[]},'原稿句子。')


if __name__=='__main__':
    unittest.main()
