from decimal import Decimal

def group_checks(state):
    # 组内核对：分摊回各单的损耗、成本与库存扣减必须分别等于组合计。
    demands={d['id']:d for d in state.get('demands',[])}
    calculations={r['id']:r for r in state.get('calculations',[])}
    out=[]
    for g in state.get('groups',[]):
        members=g['members']
        sheets=all(sum(demands[m][k] for m in members)==g[k] for k in ('net','fixed','variable','gross'))
        cost=sum((Decimal(calculations[m]['cost']) for m in members),Decimal(0))==Decimal(str(g.get('cost','0.00')))
        deducted=sum(calculations[m]['opening']-calculations[m]['closing'] for m in members)
        stock=deducted==(g['gross'] if g.get('released') else 0)
        out.append({'id':g['id'],'members':members,'sheets_balanced':sheets,'cost_balanced':cost,'stock_balanced':stock,'balanced':sheets and cost and stock})
    return out

def balance(state):
    accepted=len(state['rows']);isolated=len(state['quarantine']);accounted=accepted+isolated+state['blank_count']+state['header_count']+state['duplicate_count']
    cost=sum((Decimal(r['cost']) for r in state['calculations']),Decimal(0));target=Decimal(state['business']['total'])
    stock_ok=all(l['opening']==l['consumed']+l['closing'] for l in state['lots'])
    groups=group_checks(state);groups_ok=all(g['balanced'] for g in groups)
    return {'input':state['input_count'],'accepted':accepted,'isolated':isolated,'blank':state['blank_count'],'headers':state['header_count'],'duplicates':state['duplicate_count'],'accounted':accounted,'balanced':accounted==state['input_count'] and cost==target and stock_ok and groups_ok,'cost_balanced':cost==target,'stock_balanced':stock_ok,'groups':groups,'groups_balanced':groups_ok,'business':state['business']}
