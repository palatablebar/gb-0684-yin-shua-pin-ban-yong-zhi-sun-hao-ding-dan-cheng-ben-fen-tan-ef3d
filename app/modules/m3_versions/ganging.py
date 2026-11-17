from datetime import date
from decimal import Decimal
from app.errors import DomainError

SPEC_DIMS=('paper_w','paper_h','piece_w','piece_h','bleed','gap')

def spec_key(item):
    # 同纸同规格：同纸批、同尺寸(统一mm后按Decimal数值)、同纹向、同损耗参数。
    dims=item['dims'];source=item['source']
    return (item['lot'],)+tuple(Decimal(str(dims[k])) for k in SPEC_DIMS)+(str(source['grain']),Decimal(str(source['fixed_loss'])),Decimal(str(source['loss_pct'])))

def parse(parameters):
    ganging=(parameters or {}).get('ganging')
    if ganging in (None,'solo'):return {'mode':'solo','groups':[],'window_days':None}
    if isinstance(ganging,str):
        if ganging=='auto':return {'mode':'auto','groups':[],'window_days':None}
        raise DomainError('GANGING','合版参数无效')
    if not isinstance(ganging,dict):raise DomainError('GANGING','合版参数无效')
    window=ganging.get('window_days')
    if window is not None and (isinstance(window,bool) or not isinstance(window,int) or window<0):raise DomainError('GANGING','合版窗口天数无效')
    if ganging.get('mode') in (None,'custom') and 'groups' in ganging:
        groups=ganging['groups']
        if not isinstance(groups,list) or any(not isinstance(members,list) or len(members)<2 for members in groups):raise DomainError('GANGING','合版分组须为至少两张订单的列表')
        flat=[member for members in groups for member in members]
        if any(not isinstance(member,str) for member in flat) or len(set(flat))!=len(flat):raise DomainError('GANGING','合版分组成员无效或重复')
        return {'mode':'custom','groups':groups,'window_days':window}
    mode=ganging.get('mode','solo')
    if mode not in ('solo','auto'):raise DomainError('GANGING','合版模式无效')
    return {'mode':mode,'groups':[],'window_days':window}

def _group(lot,members):
    # 生产日取组内最早交期：交期紧的单不为省纸等待晚单，晚单合版即提前生产。
    return {'lot':lot,'production_date':members[0]['due'],'members':[m['id'] for m in members],'copies':members[0]['choice']['copies']}

def propose(layouts,window_days):
    specs={}
    for item in layouts:specs.setdefault(spec_key(item),[]).append(item)
    groups=[]
    for key in specs:
        current=[]
        for item in sorted(specs[key],key=lambda o:(o['due'],o['id'])):
            if current and window_days is not None and (date.fromisoformat(item['due'])-date.fromisoformat(current[0]['due'])).days>window_days:
                groups.append(_group(key[0],current));current=[]
            current.append(item)
        if current:groups.append(_group(key[0],current))
    return sorted(groups,key=lambda g:(g['lot'],g['production_date'],g['members'][0]))

def _number(groups):
    for n,g in enumerate(groups,1):g['id']='G%d'%n
    return groups

def adjudicate(state):
    layouts=state['layouts'];params=parse(state.get('parameters'))
    proposal=_number([g for g in propose(layouts,params['window_days']) if len(g['members'])>1])
    by_id={o['id']:o for o in layouts}
    spec_sizes={}
    for o in layouts:spec_sizes[spec_key(o)]=spec_sizes.get(spec_key(o),0)+1
    if params['mode']=='custom':
        applied=[]
        for members in params['groups']:
            missing=[m for m in members if m not in by_id]
            if missing:raise DomainError('GANGING','合版订单不存在: '+'、'.join(missing))
            if len({spec_key(by_id[m]) for m in members})!=1:raise DomainError('GANGING','同组工单须同纸同规格同损耗参数')
            ordered=sorted((by_id[m] for m in members),key=lambda o:(o['due'],o['id']))
            applied.append(_group(ordered[0]['lot'],ordered))
        applied=_number(sorted(applied,key=lambda g:(g['lot'],g['production_date'],g['members'][0])))
    elif params['mode']=='auto':applied=[dict(g) for g in proposal]
    else:applied=[]
    member_of={m:g for g in applied for m in g['members']}
    reasons={}
    for o in layouts:
        oid=o['id']
        if oid in member_of:
            g=member_of[oid]
            if oid==g['members'][0]:reasons[oid]={'code':'ANCHOR','text':'组内最早交期，定为生产日'}
            else:
                days=(date.fromisoformat(o['due'])-date.fromisoformat(g['production_date'])).days
                reasons[oid]={'code':'MERGED','text':'同纸同规格合入%s，提前%d天生产'%(g['id'],days)}
        elif params['mode']=='custom':reasons[oid]={'code':'SOLO_DECISION','text':'裁决未列入，单独开版'}
        elif params['mode']=='auto':
            if spec_sizes[spec_key(o)]>1:reasons[oid]={'code':'SOLO_WINDOW','text':'超出合版窗口，单独开版'}
            else:reasons[oid]={'code':'SOLO_SPEC','text':'无同纸同规格工单，单独开版'}
        else:reasons[oid]={'code':'SOLO_DEFAULT','text':'未采纳合版，逐单开版'}
    labels={'solo':'逐单开版','auto':'按裁决合版','custom':'按指定分组合版'}
    state['grouping']={'mode':params['mode'],'mode_label':labels[params['mode']],'window_days':params['window_days'],'applied':applied,'proposal':proposal,'reasons':reasons}
    return state
