import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'backend'))
from engine import calculate, validate

BASE = {'outage_start': 6, 'outage_duration': 5, 'late_rate': 350, 'jobs': [
 {'id':'Bread', 'duration':4, 'deadline':9, 'missed_penalty':4600},
 {'id':'Cake', 'duration':5, 'deadline':8, 'missed_penalty':7800},
 {'id':'Biscuits', 'duration':3, 'deadline':19, 'missed_penalty':2400},
 {'id':'Pastries', 'duration':4, 'deadline':16, 'missed_penalty':3900},
 {'id':'Tea', 'duration':3, 'deadline':23, 'missed_penalty':2100}]}

class EngineTests(unittest.TestCase):
 def test_better_or_equal(self):
  r=calculate(BASE)
  self.assertLessEqual(r['optimized']['loss'],r['baseline']['loss'])
  self.assertEqual(r['solver_status'],'OPTIMAL')
 def test_schedules_are_valid(self):
  for scenario in (BASE, {**BASE, 'backup':True}, {**BASE, 'outage_start':0,'outage_duration':24}, {**BASE,'outage_duration':0}):
   r=calculate(scenario)
   for key in ('baseline','optimized'):
    sched=sorted(r[key]['schedule'],key=lambda x:x['start'])
    self.assertEqual(len(set(x['id'] for x in sched)),len(sched))
    for i,j in enumerate(sched):
     self.assertTrue(0<=j['start']<j['end']<=24)
     if i:self.assertLessEqual(sched[i-1]['end'],j['start'])
     if not scenario.get('backup',False) and scenario['outage_duration']:
      self.assertTrue(j['end'] <= scenario['outage_start'] or j['start'] >= scenario['outage_start']+scenario['outage_duration'])
 def test_validation(self):
  with self.assertRaises(ValueError):calculate({**BASE,'outage_duration':24})
  with self.assertRaises(ValueError):calculate({**BASE,'jobs':[BASE['jobs'][0]]*2})
 def test_zero_loss(self):
  r=calculate({'jobs':[{'id':'One','duration':1,'deadline':24,'missed_penalty':100}], 'outage_start':0,'outage_duration':0,'late_rate':200})
  self.assertEqual(r['savings'],0)
  self.assertEqual(r['improvement_percent'],0)

if __name__=='__main__':unittest.main()
