import pytest
from checker import analyze, format_sql

def grouping(sql):
    return [i for i in analyze(sql)['issues'] if i['code'].startswith('GROUP_')]

def errors(sql): return [i for i in grouping(sql) if i['severity']=='error']

@pytest.mark.parametrize('sql,code,field',[
    ('select a,b,sum(c) from t group by a','GROUP_NON_AGGREGATE','b'),
    ('select a,sum(b) from t','GROUP_BY_MISSING','a'),
    ('select a+sum(b) from t group by c','GROUP_NON_AGGREGATE','a'),
    ('select a,count(*) from t group by a+1','GROUP_NON_AGGREGATE','a'),
    ('select a,b,count(*) from t group by 1','GROUP_NON_AGGREGATE','b'),
    ("select if(a is null,'空',a) as area,count(*) from t group by b",'GROUP_NON_AGGREGATE','a'),
    ('select a,count(*) from t group by 3','GROUP_POSITION_INVALID','3'),
    ('select a,sum(b) from t group by sum(b)','GROUP_AGGREGATE_KEY','SUM'),
])
def test_group_mismatches_are_priority_zero(sql,code,field):
    items=errors(sql)
    match=next(i for i in items if i['code']==code)
    assert match['priority']==0 and field.lower() in match['reason'].lower()

@pytest.mark.parametrize('sql',[
    'select a,sum(b) from t group by a',
    'select a+1,sum(b) from t group by a',
    'select year(a)+1,count(*) from t group by year(a)',
    'select year(a),count(*) from t group by year(a)',
    "select if(a is null,'空',a) as area,count(*) from t group by if(a is null,'空',a)",
    "select if(a is null,'空',a) as area,count(*) from t group by area",
    'select a as dimension,count(*) from t group by 1',
    'select a, b,sum(c) from t group by 1,2',
    'select t.a,count(*) from t group by a',
    'select a,count(*) from t group by t.a',
    'select a, sum(b) filter(where c>0) from t group by a',
    'select sum(a),count(*) from t',
    'select 1, sum(a) from t',
    'select a,sum(b) over(partition by c) from t',
    'select a,count(*),row_number() over(order by a) from t group by a',
    'select a, sum(sum(b)) over() from t group by a',
    'select x.a from (select a,sum(b) from t group by a) x',
    'select a from t group by a',
    'select A,COUNT(*) from t group by a',
])
def test_legal_grouping_aliases_positions_and_windows(sql):
    assert not errors(sql)

def test_hidden_group_dimension_is_a_risk_not_syntax_error():
    item=next(i for i in grouping('select a,sum(c) from t group by a,b') if i['code']=='GROUP_KEY_NOT_PROJECTED')
    assert item['priority']==0 and item['severity']=='warning'
    assert '可以合法' in item['suggestion']

def test_inner_aggregate_does_not_force_outer_grouping():
    assert not errors('select a,(select sum(b) from u) as total from t')

def test_window_reference_on_ungrouped_field_is_detected():
    assert errors('select a,count(*),row_number() over(order by b) from t group by a')

def test_nested_window_aggregate_requires_grouping_for_other_output():
    assert any(i['code']=='GROUP_BY_MISSING' for i in errors('select a,sum(sum(b)) over() from t'))

def test_rollup_uses_real_dimensions_instead_of_skipping_validation():
    assert not errors('select a,sum(b) from t group by rollup(a)')
    assert errors('select a,c,sum(b) from t group by rollup(a)')

def test_wildcard_needs_database_expansion():
    items=grouping('select *,count(*) from t group by a')
    assert any(i['code']=='GROUP_WILDCARD_UNVERIFIED' for i in items)

def test_location_and_order_precede_general_warnings():
    sql='select\n    a\n    ,b\n    ,sum(c)\nfrom t\ngroup by a'
    first=analyze(sql)['issues'][0]
    assert first['code']=='GROUP_NON_AGGREGATE' and first['line']==3 and first['column']==6


def test_api_and_formatter_keep_the_business_error_visible():
    from app import app
    sql='select a,b,sum(c) from t group by a'
    first=app.test_client().post('/api/check',json={'sql':sql}).get_json()['issues'][0]
    assert first['code']=='GROUP_NON_AGGREGATE' and first['priority']==0
    assert errors(format_sql(sql))

def test_different_same_length_templates_do_not_hide_group_expression_mismatch():
    sql="select if(dt='${month_1}','是','否') as period,count(*) from t group by if(dt='${month_2}','是','否')"
    items=errors(sql)
    assert any(i['code']=='GROUP_NON_AGGREGATE' for i in items)
    assert '${month_1}' in items[0]['reason']

def test_same_template_expression_is_accepted_and_stays_on_original_line():
    sql="select\n    if(dt='${month_1}','是','否') as period\n    ,count(*)\nfrom t\ngroup by if(dt='${month_1}','是','否')"
    assert not errors(sql)
    assert '${month_1}' in format_sql(sql)


def test_aggregate_alias_needs_schema_confirmation_not_definitive_error():
    items=grouping('select sum(b) as total from t group by total')
    assert any(i['code']=='GROUP_AGGREGATE_KEY' and i['severity']=='warning' and i['priority']==0 for i in items)


def test_aggregate_alias_matching_real_input_is_not_a_group_syntax_error():
    assert not errors('select sum(b) as b from t group by b')


@pytest.mark.parametrize('sql',[
    'select a.region,count(*) from t a join u b on a.id=b.id group by region',
    'select region,count(*) from t a join u b on a.id=b.id group by a.region',
])
def test_multi_source_bare_qualified_match_requires_schema_not_certain_error(sql):
    assert not errors(sql)
    assert any(i['code']=='GROUP_COLUMN_AMBIGUOUS' and i['priority']==0 for i in grouping(sql))


def test_two_explicitly_different_table_fields_still_raise_group_error():
    sql='select a.region,count(*) from t a join u b on a.id=b.id group by b.region'
    assert any(i['code']=='GROUP_NON_AGGREGATE' for i in errors(sql))
