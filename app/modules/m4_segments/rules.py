from decimal import Decimal,ROUND_CEILING

def losses(quantity,copies,fixed,percent):
    q=Decimal(str(quantity));p=Decimal(str(percent));f=Decimal(str(fixed))
    net=int((q/Decimal(copies)).to_integral_value(rounding=ROUND_CEILING));variable=int((Decimal(net)*p/100).to_integral_value(rounding=ROUND_CEILING))
    return {'net':net,'fixed':int(f),'variable':variable,'gross':net+int(f)+variable,'capacity':net*copies,'overprint':net*copies-int(q)}

def apportion_int(total,weights):
    # 共享张数按印量比例最大余数分摊到整数张，组内分摊合计必等于组合计。
    weights=[Decimal(str(w)) for w in weights]
    if total<=0 or not weights:return [0]*len(weights)
    whole=sum(weights);exact=[Decimal(total)*w/whole for w in weights]
    base=[int(e) for e in exact];rest=int(total)-sum(base)
    for i in sorted(range(len(weights)),key=lambda i:(-(exact[i]-base[i]),i))[:rest]:base[i]+=1
    return base

def _exact_cost(gross,layout):
    dims=layout['dims'];source=layout['source']
    weight=Decimal(str(gross))*Decimal(dims['paper_w'])*Decimal(dims['paper_h'])/Decimal(1000000)*Decimal(str(source['gsm']))/Decimal(1000)
    return weight*Decimal(str(source['price_kg']))

def _shares(members,quantities,copies,total):
    nets=apportion_int(total['net'],quantities);fixeds=apportion_int(total['fixed'],quantities);variables=apportion_int(total['variable'],quantities)
    return nets,fixeds,variables

def _compare(grouping,by_id):
    # 晚单可合版时，分别给出合并与分开的排数、损耗与精确成本(未做分币分摊)。
    out=[]
    for g in grouping.get('proposal',[]):
        members=[by_id[m] for m in g['members']]
        quantities=[Decimal(str(m['source']['quantity'])) for m in members]
        first=members[0]['source']
        total=losses(sum(quantities),g['copies'],first['fixed_loss'],first['loss_pct'])
        nets,fixeds,variables=_shares(members,quantities,g['copies'],total)
        for index,m in enumerate(members):
            if index==0:continue
            source=m['source']
            solo=losses(quantities[index],g['copies'],source['fixed_loss'],source['loss_pct'])
            share={'net':nets[index],'fixed':fixeds[index],'variable':variables[index],'gross':nets[index]+fixeds[index]+variables[index]}
            solo_cost=_exact_cost(solo['gross'],m);merged_cost=_exact_cost(share['gross'],m)
            out.append({'order':m['id'],'group':g['id'],'production_date':g['production_date'],
                'solo':{'net':solo['net'],'fixed':solo['fixed'],'variable':solo['variable'],'gross':solo['gross'],'cost':str(solo_cost.quantize(Decimal('0.0001')))},
                'merged':{'net':share['net'],'fixed':share['fixed'],'variable':share['variable'],'gross':share['gross'],'cost':str(merged_cost.quantize(Decimal('0.0001')))},
                'saved':{'sheets':solo['gross']-share['gross'],'cost':str((solo_cost-merged_cost).quantize(Decimal('0.0001')))}})
    return out

def apply(state):
    grouping=state.get('grouping') or {}
    by_id={l['id']:l for l in state['layouts']}
    demands=[];groups=[]
    for g in grouping.get('applied',[]):
        members=[by_id[m] for m in g['members']]
        quantities=[Decimal(str(m['source']['quantity'])) for m in members]
        first=members[0]['source']
        # 一次拼版生产：合并印量只开一次版，固定开机损耗全组共担一次。
        total=losses(sum(quantities),g['copies'],first['fixed_loss'],first['loss_pct'])
        nets,fixeds,variables=_shares(members,quantities,g['copies'],total)
        groups.append({'id':g['id'],'lot':g['lot'],'production_date':g['production_date'],'members':list(g['members']),'copies':g['copies'],'quantity':str(sum(quantities)),'net':total['net'],'fixed':total['fixed'],'variable':total['variable'],'gross':total['gross'],'capacity':total['capacity'],'overprint':total['overprint']})
        for m,quantity,net,fixed,variable in zip(members,quantities,nets,fixeds,variables):
            demands.append({'net':net,'fixed':fixed,'variable':variable,'gross':net+fixed+variable,'capacity':net*g['copies'],'overprint':net*g['copies']-int(quantity),'group':g['id'],'shared':True,**m})
    grouped_ids={m for g in grouping.get('applied',[]) for m in g['members']}
    for l in state['layouts']:
        if l['id'] in grouped_ids:continue
        r=l['source'];result=losses(r['quantity'],l['choice']['copies'],r['fixed_loss'],r['loss_pct']);result.update(l);result['group']=None;result['shared']=False;demands.append(result)
    order={l['id']:i for i,l in enumerate(state['layouts'])}
    demands.sort(key=lambda d:order[d['id']])
    state['demands']=demands;state['groups']=groups;state['comparison']=_compare(grouping,by_id)
    return state
