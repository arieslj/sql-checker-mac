import pytest
from checker import analyze, format_sql
from app import app

def codes(sql): return {i['code'] for i in analyze(sql)['issues']}
@pytest.mark.parametrize('sql,code', [
    ('select a，b from t','FULLWIDTH'),
    ('select a from t group by a,','GROUP_TRAILING_COMMA'),
    ('select a.id from t a join u b on a.id=a.id','SELF_JOIN_CONDITION'),
    ('select z.id from t a','UNDEFINED_ALIAS'),
    ('select amount / cnt from t','DIVISION_ZERO'),
    ('select a,b,count(*) from t group by a','GROUP_NON_AGGREGATE'),
    ("select * from t where dt between '2026-10-01' and '2026-10-08'",'DATE_BOUNDARY'),
    ('select * from t a join u b on a.id=b.id','JOIN_MULTIPLICATION'),
    ('select ( from t','PARSE'),
])
def test_rules(sql,code): assert code in codes(sql)

def test_fullwidth_literals_comments():
    assert 'FULLWIDTH' not in codes("select '中文，（）' as `备注` -- ，\nfrom t")
def test_scope_and_correlation():
    assert 'UNDEFINED_ALIAS' not in codes('select a.id from t a where exists (select 1 from u b where b.id=a.id)')
    assert 'UNDEFINED_ALIAS' in codes('select b.id from (select b.id from t b) a')
def test_templates_functions():
    sql="select get_json_object(payload, '$.sceneParams.unloadingVehicleImage'), date_sub('${dt}', 7), nvl(a,0), custom_dli_func(a) from t where dt='${month_1}'"
    assert 'PARSE' not in codes(sql)
    result=format_sql(sql)
    assert '${dt}' in result and '${month_1}' in result
    assert '$.sceneParams.unloadingVehicleImage' in result

def test_safe_division_grouping():
    assert 'DIVISION_ZERO' not in codes('select amount / nullif(cnt,0) from t')
    assert 'GROUP_NON_AGGREGATE' not in codes('select a, sum(b) from t group by a')
    assert 'GROUP_NON_AGGREGATE' not in codes('select a+1, count(*) from t group by a')
def test_line_mapping():
    items=analyze('select\n    a / b\nfrom t')['issues']
    assert next(i for i in items if i['code']=='DIVISION_ZERO')['line']==2

def test_format_preserves():
    original="SELECT\n    a,\n    b,\n    '${dt}' AS `中文别名` -- Keep CASE\nFROM t;"
    result=format_sql(original)
    assert 'select' in result and 'SELECT' not in result
    assert '\n    ,b' in result or '\n    , b' in result
    assert "'${dt}'" in result and '-- Keep CASE' in result
    assert format_sql(result)==result

def test_api():
    client=app.test_client()
    assert client.get('/').status_code==200
    assert client.post('/api/check',json={'sql':'select 1'}).status_code==200
    assert client.post('/api/check',json={'sql':''}).status_code==400
    assert client.post('/api/check',json={'sql':1}).status_code==400
    assert client.post('/api/check',json={'sql':'x'*50001}).status_code==400
    assert client.post('/api/check',json={'sql':'select 1'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/format',json={'sql':'select ( from t'}).status_code==400
    assert 'no-store' in client.get('/').headers['Cache-Control']

def test_mixed_aggregate():
    assert 'GROUP_NON_AGGREGATE' in codes('select b + sum(c) from t group by a')

def test_cte_window():
    assert 'UNDEFINED_ALIAS' not in codes('with x as (select a from t) select x.a from x')
    assert 'GROUP_NON_AGGREGATE' not in codes('select a, row_number() over(order by a) as rn from t group by a')

def test_host_validation():
    assert app.test_client().get('/',headers={'Host':'evil.example'}).status_code==400

def test_trailing_comma_subquery():
    assert 'GROUP_TRAILING_COMMA' in codes('select * from (select a from t group by a,) x')
    assert 'GROUP_TRAILING_COMMA' not in codes('select a from t group by concat(a,b)')

def test_unterminated_literal():
    assert 'PARSE' in codes("select 'oops")
