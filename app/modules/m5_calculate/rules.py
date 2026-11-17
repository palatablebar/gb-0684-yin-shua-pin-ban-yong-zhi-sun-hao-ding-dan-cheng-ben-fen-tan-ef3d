from decimal import Decimal,ROUND_DOWN,ROUND_HALF_UP
from collections import defaultdict
from app.errors import DomainError

def apportion(values,target=None):
    values=[Decimal(str(v)) for v in values]
    if target is None:target=sum(values,Decimal(0)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    else:target=Decimal(str(target))
    allocated=[v.quantize(Decimal('.01'),rounding=ROUND_DOWN) for v in values]
    pennies=int((target-sum(allocated))/Decimal('.01'))
    if pennies>0:
        for i in sorted(range(len(values)),key=lambda i:(-(values[i]-allocated[i]),i))[:pennies]:allocated[i]+=Decimal('.01')
    elif pennies<0:
        for i in sorted(range(len(values)),key=lambda i:(values[i]-allocated[i],i))[:-pennies]:
            if allocated[i]>=Decimal('.01'):allocated[i]-=Decimal('.01')
    return allocated

def apply(state):
    grouped=defaultdict(list)
    for d in state['demands']:grouped[d['lot']].append(d)
    group_meta={g['id']:g for g in state.get('groups',[])}
    for g in group_meta.values():g.update(released=False,cost='0.00',shortage=0)
    calculations=[];lots=[]
    for lot,orders in sorted(grouped.items()):
        contracts={tuple(Decimal(str(v)) for v in (o['source']['stock'],o['source']['gsm'],o['source']['price_kg'],o['dims']['paper_w'],o['dims']['paper_h'])) for o in orders}
        if len(contracts)!=1:raise DomainError('CONFLICT','同纸批库存或材质定义冲突')
        stock=int(Decimal(str(orders[0]['source']['stock'])));opening=stock
        units={}
        for o in orders:units.setdefault(o.get('group') or '~'+o['id'],[]).append(o)
        sequence=[]
        for key,members in units.items():
            members.sort(key=lambda o:(o['due'],o['id']))
            sequence.append((members[0]['due'],members[0]['id'],key,members))
        sequence.sort(key=lambda u:(u[0],u[1]))
        ready=[]
        for _,_,key,members in sequence:
            # 合版组整组放行：不足整组不放行，库存不为负；放行后按成员分摊量逐单过账。
            need=sum(o['gross'] for o in members);enough=need<=stock;exact=[];items=[]
            for o in members:
                r=o['source'];amount=o['gross'];weight=Decimal(amount)*Decimal(o['dims']['paper_w'])*Decimal(o['dims']['paper_h'])/1000000*Decimal(str(r['gsm']))/1000
                closing=stock-amount if enough else stock
                item={'id':o['id'],'line':o['line'],'lot':lot,'group':o.get('group'),'copies':o['choice']['copies'],'rotated':o['choice']['rotated'],'net':o['net'],'fixed_loss':o['fixed'],'run_loss':o['variable'],'gross':amount,'opening':stock,'closing':closing,'shortage':max(0,amount-stock),'weight_kg':str(weight),'cost':'0.00','code':'RELEASED' if enough else 'SHORTAGE'}
                calculations.append(item);items.append(item)
                if enough:exact.append(weight*Decimal(str(r['price_kg'])));stock=closing
            if key in group_meta:
                group_meta[key]['released']=enough
                if not enough:group_meta[key]['shortage']=need-stock
            if enough:ready.append((key,items,exact))
        # 先按纸批精确总成本最大余额分摊到生产单元(组或单)，组内再按各单精确成本分摊到订单。
        unit_costs=apportion([sum(exact) for _,_,exact in ready])
        for (key,items,exact),cost in zip(ready,unit_costs):
            if len(items)==1:items[0]['cost']=str(cost)
            else:
                for item,member_cost in zip(items,apportion(exact,target=cost)):item['cost']=str(member_cost)
            if key in group_meta:group_meta[key]['cost']=str(cost)
        lots.append({'id':lot,'opening':opening,'closing':stock,'consumed':opening-stock,'cost':str(sum(unit_costs,Decimal(0)))})
    state['calculations']=calculations;state['lots']=lots;state['business']={'total':str(sum((Decimal(l['cost']) for l in lots),Decimal(0))),'sheets':sum(l['consumed'] for l in lots),'leftover':sum(l['closing'] for l in lots),'shortage_orders':sum(r['code']=='SHORTAGE' for r in calculations),'unit':'CNY'};return state
