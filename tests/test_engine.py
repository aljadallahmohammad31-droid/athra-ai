import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
class EngineTests(unittest.TestCase):
 def test_arabic_alias_match_and_impact_path(self):
  r=app.repo(); fs=app.analyze([{'source':'فقرة 1','text':'يجب على خدمة البيان الجمركي استدعاء واجهة التحقق من الإفراج قبل الإفراج.'}],r)
  self.assertTrue(fs[0]['matched_components'])
  self.assertTrue(fs[0]['candidate_impacts'])

 def test_synthetic_repository_has_fifteen_modules_and_valid_relationships(self):
  r=app.repo(); ids={c['id'] for c in r['components']}
  self.assertEqual(len(r['components']),15)
  self.assertTrue(all(x['from'] in ids and x['to'] in ids for x in r['relationships']))
  self.assertTrue(r['system']['synthetic'])

 def test_text_extract(self):
  p=app.extract('x.txt','يجب التحقق\nسطر ثاني'.encode())
  self.assertEqual(len(p),2)
 def test_unrelated_text_no_match(self):
  fs=app.analyze([{'source':'فقرة 1','text':'نص عام لا يذكر أي مكوّن معروف.'}],app.repo())
  self.assertEqual(fs[0]['matched_components'],[])
 def test_role_aware_document_metadata(self):
  sample=Path(__file__).resolve().parents[1]/'samples_ar'/'BRD_AR_01.docx'
  result=app.analyze_files([('change',sample.name,sample.read_bytes())])
  self.assertEqual(result['documents'][0]['role'],'change')
  self.assertIn('role_label',result['documents'][0])
 def test_pdf_report_is_generated(self):
  if not app.REPORTLAB: self.skipTest('reportlab not installed')
  pdf=app.build_pdf_report({'documents':[],'findings':[]})
  self.assertTrue(pdf.startswith(b'%PDF'))
if __name__=='__main__': unittest.main()
