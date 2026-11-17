import json
from decimal import Decimal
import pytest
from app.workflow import run,load
from app.errors import DomainError
from app.modules.m4_segments.rules import apportion_int
from app.modules.m5_calculate.rules import apportion,apply
from app.modules.m6_reconcile.compare import balance
from app import store

@pytest.fixture
def auto():return run(load('clean.csv'),{'ganging':'auto'})

def test_default_stays_solo():
    s=run(load('clean.csv'),{})
    assert s['grouping']['mode']=='solo' and s['grouping']['applied']==[] and s['business']['sheets']==4392

def test_proposal_same_paper_same_spec():
    s=run(load('clean.csv'),{})
    groups=s['grouping']['proposal']
    assert len(groups)==3 and all(len(g['members'])==12 for g in groups)
    assert all(g['production_date']=='2026-11-17' for g in groups)

def test_auto_shared_startup_once(auto):
    assert auto['business']['sheets']==3732 and auto['business']['leftover']==2268
    g=auto['groups'][0]
    assert (g['net'],g['fixed'],g['variable'],g['gross'])==(1200,20,24,1244)

def test_allocation_conserves_group_totals(auto):
    for g in auto['groups']:
        members=[d for d in auto['demands'] if d.get('group')==g['id']]
        for key in ('net','fixed','variable','gross'):assert sum(d[key] for d in members)==g[key]

def test_apportion_int_largest_remainder():
    assert apportion_int(20,[1000]*12)==[2]*8+[1]*4 and sum(apportion_int(7,[1,1,1]))==7

def test_cost_apportioned_back_to_orders(auto):
    assert sum(Decimal(r['cost']) for r in auto['calculations'])==Decimal(auto['business']['total'])==Decimal('1421.16')
    for g in auto['groups']:
        members=[r for r in auto['calculations'] if r['id'] in g['members']]
        assert sum(Decimal(r['cost']) for r in members)==Decimal(g['cost'])

def test_apportion_with_target():
    assert sum(apportion(['46.4576']*12))==Decimal('557.49')
    parts=apportion(['39.6032']*8+['39.2224']*4,target='473.72')
    assert sum(parts)==Decimal('473.72')

def test_late_order_merge_vs_split(auto):
    row=next(c for c in auto['comparison'] if c['order']=='PO0002')
    assert row['solo']['gross']==122 and row['merged']['gross']==104 and row['saved']['sheets']==18
    assert Decimal(row['solo']['cost'])>Decimal(row['merged']['cost']) and row['group']=='G1'

def test_window_zero_keeps_late_orders_solo():
    s=run(load('clean.csv'),{'ganging':{'mode':'auto','window_days':0}})
    assert s['grouping']['applied']==[] and s['business']['sheets']==4392

def test_window_splits_groups():
    s=run(load('clean.csv'),{'ganging':{'mode':'auto','window_days':5}})
    assert len(s['groups'])==6 and all(len(g['members'])==6 for g in s['groups'])
    assert s['business']['sheets']==3792

def test_custom_groups():
    s=run(load('clean.csv'),{'ganging':{'groups':[['PO0002','PO0001']]}})
    assert s['grouping']['mode']=='custom' and len(s['groups'])==1
    g=s['groups'][0];assert g['members']==['PO0001','PO0002'] and g['gross']==224
    assert s['business']['sheets']==4372

def test_custom_unknown_order_rejected():
    with pytest.raises(DomainError) as e:run(load('clean.csv'),{'ganging':{'groups':[['PO0001','NOPE']]}})
    assert e.value.code=='GANGING'

def test_custom_mixed_spec_rejected():
    with pytest.raises(DomainError) as e:run(load('clean.csv'),{'ganging':{'groups':[['PO0001','PO0013']]}})
    assert e.value.code=='GANGING'

def test_custom_duplicate_member_rejected():
    with pytest.raises(DomainError) as e:run(load('clean.csv'),{'ganging':{'groups':[['PO0001','PO0002'],['PO0002','PO0003']]}})
    assert e.value.code=='GANGING'

def test_singleton_group_rejected():
    with pytest.raises(DomainError) as e:run(load('clean.csv'),{'ganging':{'groups':[['PO0001']]}})
    assert e.value.code=='GANGING'

def test_bad_ganging_param_rejected():
    with pytest.raises(DomainError):run(load('clean.csv'),{'ganging':{'window_days':-1}})

def test_reasons_explain_choices(auto):
    reasons=auto['grouping']['reasons']
    assert reasons['PO0001']['code']=='ANCHOR' and reasons['PO0002']['code']=='MERGED'
    assert '提前1天' in reasons['PO0002']['text']

def test_group_reconciliation_passes(auto):
    assert auto['reconcile']['balanced'] and auto['reconcile']['groups_balanced']
    assert len(auto['reconcile']['groups'])==3 and all(g['balanced'] for g in auto['reconcile']['groups'])

def test_group_reconciliation_detects_tamper(auto):
    auto['calculations'][0]['cost']='0.01'
    assert balance(auto)['groups_balanced'] is False

def test_group_shortage_blocks_whole_group():
    s=run(load('clean.csv'),{'ganging':'auto'},4)
    for d in s['demands']:d['source']['stock']='1000'
    r=apply(s)
    g=r['groups'][0]
    assert g['released'] is False and g['shortage']==244
    members=[c for c in r['calculations'] if c.get('group')=='G1']
    assert len(members)==12 and all(c['code']=='SHORTAGE' and c['closing']==1000 for c in members)

def test_export_same_caliber(auto):
    from app.modules.m7_archive.export_out import bundle
    text=bundle(auto)
    assert text.count('分组')>=3 and '对比' in text
    line=next(l for l in text.splitlines() if l.startswith('分组'))
    assert '""gross"": 1244' in line and '""production_date""' in line

def test_decide_idempotent(client):
    rid=client.post('/api/runs',json={'sample':'clean.csv'}).get_json()['run_id']
    a=client.post('/api/runs/%s/decide'%rid,json={'ganging':'auto'}).get_json()
    before=len(client.get('/api/runs').get_json())
    b=client.post('/api/runs/%s/decide'%rid,json={'ganging':'auto'}).get_json()
    after=client.get('/api/runs').get_json()
    assert a['run_id']==b['run_id'] and a['business']==b['business']
    assert len(after)==before and sum(h['id']==a['run_id'] for h in after)==1

def test_decide_failure_keeps_old_version(client):
    rid=client.post('/api/runs',json={'sample':'clean.csv'}).get_json()['run_id']
    before=client.get('/api/runs').get_json()
    r=client.post('/api/runs/%s/decide'%rid,json={'ganging':{'groups':[['PO0001','NOPE']]}})
    assert r.status_code==422 and r.get_json()['code']=='GANGING'
    assert client.get('/api/runs').get_json()==before
    assert client.get('/api/runs/%s'%rid).get_json()['business']['sheets']==4392

def test_decide_reset_returns_to_solo(client):
    rid=client.post('/api/runs',json={'sample':'clean.csv'}).get_json()['run_id']
    ganged=client.post('/api/runs/%s/decide'%rid,json={'ganging':'auto'}).get_json()
    reset=client.post('/api/runs/%s/decide'%ganged['run_id'],json={'ganging':'solo'}).get_json()
    assert reset['run_id']==rid and reset['business']['sheets']==4392

def test_seal_requires_group_reconciliation(client,tmp_path,monkeypatch):
    s=run(load('clean.csv'),{'ganging':'auto'});s['reconcile']['balanced']=False
    monkeypatch.setenv('DB_PATH',str(tmp_path/'seal.db'));store.save(s['run_id'],s)
    with pytest.raises(DomainError) as e:store.review(s['run_id'],1,'通过')
    assert e.value.code=='UNBALANCED'

def test_seal_after_group_reconciliation(auto,tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'seal.db'));store.save(auto['run_id'],auto)
    assert store.review(auto['run_id'],1,'通过')['review_version']==2
