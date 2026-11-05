import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from practice_content import TEXTS, WORDS, WORD_GROUPS
from server import PRACTICE_SETS, practice_index, complete_practice


class PracticeContentTest(unittest.TestCase):
    def test_content_coverage(self):
        self.assertGreaterEqual(len(WORDS),300)
        self.assertGreaterEqual(len(TEXTS),90)
        self.assertEqual(len({text for _,text in WORDS}),len(WORDS))
        self.assertEqual(len({text for _,text in TEXTS}),len(TEXTS))
        self.assertGreaterEqual(len(WORD_GROUPS),8)
        for category,text in WORDS+TEXTS:
            self.assertTrue(category)
            self.assertTrue(text.strip())
            self.assertNotIn('\n',text)
        for category in ('속담','명언','고전 문학','창작 연습 문장'):
            self.assertTrue(any(label.startswith(category) for label,_ in TEXTS))

    def test_shuffle_cycles_and_menu_switch(self):
        session={}
        for kind in ('words','short'):
            indexes=[]
            for _ in range(len(PRACTICE_SETS[kind])):
                index=practice_index(session,kind)
                # Reopening a menu or retrying must not skip the current item.
                self.assertEqual(practice_index(session,kind),index)
                practice_index(session,'keys')
                self.assertEqual(practice_index(session,kind),index)
                indexes.append(index)
                complete_practice(session,kind,index)
            self.assertEqual(set(indexes),set(range(len(PRACTICE_SETS[kind]))))
            self.assertNotEqual(practice_index(session,kind),indexes[-1])
        self.assertEqual(practice_index(session,'keys'),0)
        complete_practice(session,'keys',0)
        self.assertEqual(practice_index(session,'keys'),1)

if __name__ == '__main__':
    unittest.main()
