import pytest
from checker import analyze
from app import app

# Synthetic tables; same expression/alias structure as the reported regression.
REPORTED_SHAPE = '''select
    if(ocd.plate_number rlike '挂', '挂车', '主车') 车型
    ,fir_memo 驳回原因
    ,count(cal.id) 计数
from (
    select *, substring_index(memo, ';', 1) fir_memo
    from synthetic_auth_log
    where dt=date_sub(current_date,1)
) cal
left join (select * from synthetic_driving) ocd on ocd.id=cal.car_driving_id
group by rollup(if(ocd.plate_number rlike '挂', '挂车', '主车'))'''

def issues(sql): return analyze(sql)['issues']
def errors(sql): return [i for i in issues(sql) if i['severity']=='error' and i['code'].startswith(('GROUP','WHERE_'))]


def test_reported_if_rlike_rollup_missing_reason_is_first():
    first=issues(REPORTED_SHAPE)[0]
    assert first['code']=='GROUP_NON_AGGREGATE' and first['priority']==0
    assert first['line']==3 and 'fir_memo' in first['reason']
    fixed=REPORTED_SHAPE.replace("group by rollup(","group by fir_memo, rollup(")
    assert not errors(fixed)

@pytest.mark.parametrize('clause',[
    'rollup(a)', 'a with rollup', 'cube(a)', 'a with cube',
    'grouping sets((a),())', 'a grouping sets((a),())',
    'rollup((a))', 'grouping sets(rollup(a))',
])
def test_missing_field_is_detected_in_each_grouping_syntax(clause):
    result=errors(f'select a,b,count(*) from synthetic_data group by {clause}')
    assert any(i['code']=='GROUP_NON_AGGREGATE' and 'b' in i['reason'] and i['priority']==0 for i in result)

@pytest.mark.parametrize('clause',[
    'rollup(a,b)', 'a,b with rollup', 'cube(a,b)', 'a,b with cube',
    'grouping sets((a),(b),())', 'a,b grouping sets((a),(b),())',
    'rollup((a,b))', 'cube((a,b))', 'a,rollup(b)',
    'rollup(a), cube(b)', 'grouping sets(rollup(a),cube(b))',
])
def test_declared_dimensions_do_not_have_to_exist_in_every_subtotal(clause):
    assert not errors(f'select a,b,sum(v) from synthetic_data group by {clause}')

@pytest.mark.parametrize('sql',[
    "select if(a is null,'空',a) area,count(*) from t group by rollup(if(a is null,'空',a))",
    'select a as area,count(*) from t group by rollup(area)',
    'select a,count(*) from t group by rollup(1)',
    'select a,b,c,count(*) from t group by a,rollup((b,c))',
    'select a,grouping(a),grouping_id(),count(*) from t group by rollup(a)',
    'select a,b,grouping_id(a,b),count(*) from t group by cube(a,b)',
    'select count(*) from t group by grouping sets(())',
    'select a,count(*) n from t group by rollup(a) having n>0 order by n',
    'select a,sum(v) from t where v>0 group by rollup(a) having sum(v)>1',
    'select a,count(*) from t where exists(select 1 from u having count(*)>0) group by rollup(a)',
])
def test_legitimate_advanced_queries(sql): assert not errors(sql)

@pytest.mark.parametrize('sql,code',[
    ('select a,grouping(b),count(*) from t group by rollup(a)','GROUPING_ARGUMENT_INVALID'),
    ('select grouping(a),count(*) from t group by a','GROUPING_CONTEXT_INVALID'),
    ('select a,count(*) from t group by rollup(a) having b>0','GROUP_CLAUSE_NON_AGGREGATE'),
    ('select a,count(*) from t group by cube(a) order by b','GROUP_CLAUSE_NON_AGGREGATE'),
    ('select a,count(*) from t where sum(v)>0 group by a','WHERE_AGGREGATE'),
    ('select a from t where count(*)>0','WHERE_AGGREGATE'),
    ('select count(*) from t group by rollup(sum(v))','GROUP_AGGREGATE_KEY'),
    ('select a,count(*) from t group by grouping sets(())','GROUP_NON_AGGREGATE'),
])
def test_related_dli_aggregate_rules(sql,code):
    assert any(i['code']==code and i['priority']==0 for i in errors(sql))


def test_grouping_id_incomplete_or_reordered_arguments_are_priority_risk():
    result=issues('select a,b,grouping_id(b,a),count(*) from t group by rollup(a,b)')
    assert any(i['code']=='GROUPING_ID_ARGUMENTS' and i['priority']==0 for i in result)


def test_advanced_inner_scope_does_not_leak_keys_to_outer_scope():
    sql='select x.a,x.b,count(*) from (select a,b from t group by rollup(a,b)) x group by rollup(x.a)'
    assert any(i['code']=='GROUP_NON_AGGREGATE' and 'x.b' in i['reason'] for i in errors(sql))


def test_advanced_detection_is_linear_in_declared_dimensions():
    dimensions=','.join('c'+str(i) for i in range(25))
    # No expansion into 2**25 grouping sets is necessary for field coverage.
    assert not errors(f'select {dimensions},count(*) from t group by cube({dimensions})')


def test_advanced_priority_is_present_in_api():
    response=app.test_client().post('/api/check',json={'sql':REPORTED_SHAPE})
    assert response.status_code==200
    assert response.get_json()['issues'][0]['code']=='GROUP_NON_AGGREGATE'


def test_grouping_output_alias_is_resolved_consistently():
    assert not errors('select a as dim,grouping(dim),count(*) from t group by rollup(dim)')


def test_declared_dimension_excluded_from_all_explicit_sets_is_reported():
    sql='select a,b,count(*) from t group by a,b grouping sets((a),())'
    assert not errors(sql)
    assert any(i['code']=='GROUP_KEY_ALWAYS_NULL' and i['priority']==0 for i in issues(sql))


def test_explicit_set_positions_resolve_before_dimension_comparison():
    sql='select a,b,count(*) from t group by 1,2 grouping sets((a),(b),())'
    assert not any(i['code']=='GROUP_KEY_ALWAYS_NULL' for i in issues(sql))

def test_subtotal_labels_and_distinct_cube_aggregates_are_legal():
    sql="select case when grouping(a)=1 then '总计' else a end as category, count(distinct b), count(distinct c) from t group by a with cube"
    assert not errors(sql)
