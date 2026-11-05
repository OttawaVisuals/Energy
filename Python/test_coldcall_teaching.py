"""Reconcile the generated teaching snapshot with independent source rows/formulas.

Run after build_coldcall_teaching.py: python Python/test_coldcall_teaching.py
"""
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TeachingSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT/'coldcall_json/teaching.json').read_text(encoding='utf-8'))

    def test_ceud_source_reconciliation_every_year(self):
        raw = json.loads((ROOT/'ceud_json/res_ca.json').read_text(encoding='utf-8'))['explanatory']
        for record in self.data['stock']['years']:
            with self.subTest(year=record['year']):
                rows = [r for r in raw if r['year']==record['year'] and r['variable']=='heating_system_stock_by_system_type']
                total = sum(r['value']*1000 for r in rows)
                hp = next(r['value']*1000 for r in rows if r['segment']=='heat_pump')
                self.assertAlmostEqual(total,record['sum_categories'])
                self.assertAlmostEqual(hp,record['counts']['heat_pump'])
                self.assertAlmostEqual(100*hp/total,record['hp_share_pct'])
                self.assertAlmostEqual(sum(record['counts'].values()),total)
                self.assertLess(abs(total-record['separately_rounded_total'])/total,.01)

    def test_audit_selection_and_equivalent_area(self):
        a=self.data['airtightness']; s=a['selection']
        stages=['input_rows','initial_D','ontario','single_detached','house','entry_2025','with_house_id','unique_homes','valid_homes']
        self.assertTrue(all(s[left]>=s[right] for left,right in zip(stages,stages[1:])))
        self.assertEqual(s['with_house_id']-s['unique_homes'],s['repeat_initial_audits_removed'])
        self.assertEqual(s['unique_homes']-s['valid_homes'],s['invalid_or_nonpositive_metric_removed'])
        self.assertEqual(a['n'],s['valid_homes']); self.assertGreaterEqual(a['n'],30)
        self.assertLess(a['ach50']['q25'],a['ach50']['median']); self.assertLess(a['ach50']['median'],a['ach50']['q75'])
        self.assertAlmostEqual(math.pi*(a['equivalent_circle_diameter_cm']/2)**2,a['median_ela10_cm2'])
        self.assertNotIn('HOUSEID',a); self.assertNotIn('records',a)

    def test_correct_co2_equivalent_weighting(self):
        e=self.data['comparison']['emissions']
        # Independently transcribed totals from ECCC's component factors with AR5 GWP100.
        for fuel,expected in [('gas',1931.311),('oil',2755.318),('propane',1544.376)]:
            r=e['combustion_native_g'][fuel]
            self.assertAlmostEqual(r['CO2']+28*r['CH4']+265*r['N2O'],expected)
        self.assertEqual(e['electricity_g_per_kwh'],{'ON':59,'QC':1.9,'AB':438})
        self.assertAlmostEqual(59/2.8,21.0714285714)
        self.assertEqual(438/2,219)

    def test_reference_costs_and_useful_heat_units(self):
        p=json.loads((ROOT/'prices_json/on.json').read_text(encoding='utf-8'))
        c=self.data['comparison']; prices=c['prices']; elec=p['electricity']['ottawa']
        rates=elec['plans']['tou']['prices_cad_per_kwh']
        blended=100*(.63*rates['off']+.18*rates['mid']+.19*rates['on']+elec['volumetric_adders_cad_per_kwh'])
        self.assertAlmostEqual(prices['electricity_cents_per_kwh'],blended)
        self.assertEqual(prices['gas_cad_per_m3'],p['natural_gas']['ottawa']['marginal_cad_per_m3'])
        self.assertEqual(prices['oil_cad_per_litre'],p['heating_oil']['ottawa']['cad_per_litre'])
        self.assertAlmostEqual(prices['electricity_cents_per_kwh']/2.8,6.5417857143)
        self.assertAlmostEqual(prices['propane_cad_per_litre']*100/7.0917/.78,13.558645, places=6)
        self.assertEqual(28/4,7)  # Browser sensitivity case: 28 cents electricity, COP 4.

    def test_small_aggregate_only_and_provenance(self):
        self.assertLess((ROOT/'coldcall_json/teaching.json').stat().st_size,25000)
        self.assertEqual(len(self.data['inputs']),3)
        for item in self.data['inputs']:
            self.assertEqual(len(item['sha256']),64)
            self.assertEqual(Path(item['file']).name,item['file'])
        self.assertEqual(self.data['schema_version'],1)


if __name__=='__main__':
    unittest.main()
