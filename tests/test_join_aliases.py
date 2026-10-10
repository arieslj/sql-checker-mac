import pytest
from checker import analyze

MISMATCH = '''select a1.area
from synthetic_base a1
left join synthetic_previous a5 on a5.area = a1.area and a5.region = a1.region
left join (
    select ui.area, x.region
    from synthetic_items x
    left join synthetic_users ui on ui.id = x.id
) a6 on a6.area = a1.area and a5.region = a1.region
'''

def join_issues(sql):
    return [i for i in analyze(sql)['issues'] if i['code'].startswith('JOIN_') and i['priority'] == 0]

def test_partially_wrong_alias_is_first_and_located():
    issues = analyze(MISMATCH)['issues']
    item = issues[0]
    assert item['code'] == 'JOIN_KEY_ALIAS_MISMATCH'
    assert item['severity'] == 'error' and item['priority'] == 0
    assert item['line'] == 8 and item['column'] == 31
    assert 'a5.region' in item['reason']
    assert 'a6.region = a1.region' in item['suggestion']
    assert '不是确定性语法错误' in item['suggestion']

@pytest.mark.parametrize('sql', [
    'select * from t a1 left join u a5 on a5.id=a1.id left join v a6 on a6.area=a1.area and a6.region=a1.region',
    'select * from t a1 left join u a5 on a5.id=a1.id left join v a6 on a6.id=a5.id',
    'select * from t a1 left join u a5 on a5.id=a1.id left join v a6 on a6.id=a1.id and a5.active=1',
    'select * from t a1 left join u a5 on a5.id=a1.id left join v a6 on a6.id=a1.id and a5.other_key=a1.base_key',
    'select * from t a1 left join u a5 on a5.id=a1.id left join v a6 on (a6.id=a1.id or a6.id=a5.id)',
    'select * from t a1 join u a6 on id=other_id',
    'select * from t a1 join u a6 on true',
    'select * from t a1 cross join u a6',
    'select * from t a1 join u a6 using(id)',
    'select * from t a1 join u a6 on exists(select 1 from s z where z.id=a6.id and z.id=a1.id)',
])
def test_valid_previous_alias_and_complex_predicates_are_not_blanket_errors(sql):
    assert not join_issues(sql)

def test_missing_target_alias_is_high_priority():
    result = join_issues('select * from t a1 join u a5 on a5.id=a1.id join v a6 on a5.region=a1.region')
    assert any(i['code']=='JOIN_TARGET_NOT_REFERENCED' for i in result)

def test_future_alias_in_on_is_detected():
    result = join_issues('select * from t a1 join u a6 on a6.id=a5.id join v a5 on a5.id=a1.id')
    assert any(i['code']=='JOIN_ALIAS_OUT_OF_SCOPE' for i in result)

def test_parentheses_reversed_comparisons_and_quoted_aliases():
    sql='select * from t `A1` join u `A5` on `A5`.id=`A1`.id join v `A6` on (`A1`.area=`A6`.area and `A1`.region=`A5`.region)'
    result=join_issues(sql)
    assert any(i['code']=='JOIN_KEY_ALIAS_MISMATCH' and 'A6.region' in i['suggestion'].replace('`', '') for i in result)

def test_scope_shadowing_is_local():
    sql='select * from t a1 join u a5 on a5.id=a1.id join (select * from t a1 join v a6 on a6.id=a1.id) a6 on a6.id=a1.id'
    assert not join_issues(sql)

def test_new_priority_does_not_modify_sql_or_format_logic():
    from checker import format_sql
    formatted = format_sql(MISMATCH)
    assert 'a5.region = a1.region' in formatted
    assert any(i['code']=='JOIN_KEY_ALIAS_MISMATCH' for i in join_issues(formatted))

def test_api_returns_alias_risk_before_format_and_database_warnings():
    from app import app
    response=app.test_client().post('/api/check',json={'sql':MISMATCH})
    assert response.status_code==200
    first=response.get_json()['issues'][0]
    assert first['priority']==0 and first['code']=='JOIN_KEY_ALIAS_MISMATCH'
