"""Offline Spark SQL analysis. No execution, network, or persistence."""
import re
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope
from sqlfluff.core import FluffConfig, Linter

CONFIG = FluffConfig(configs={"core": {"dialect": "sparksql", "templater": "raw", "rules": "CP01,LT01,LT02,LT04"}, "rules": {"capitalisation.keywords": {"capitalisation_policy": "lower"}}, "layout": {"type": {"comma": {"line_position": "leading"}}}})

def prepare(sql):
    # Same-width replacement preserves original line/column positions.
    return re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", lambda m: 'v' * len(m.group()), sql)

def mask(sql):
    pattern = r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|\\.|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`"
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), sql)

def analyze(sql):
    issues = []
    def add(code, level, category, reason, suggestion, node=None, offset=None):
        meta = (node.meta if node else {})
        if node and not meta:
            meta = next((x.meta for x in node.walk() if x.meta.get('line')), {})
        line, column = meta.get('line', 1), meta.get('col', 1)
        if offset is not None:
            line = sql.count('\n', 0, offset) + 1
            column = offset - sql.rfind('\n', 0, offset)
        issues.append(dict(code=code, severity=level, category=category, line=line, column=column, reason=reason, suggestion=suggestion))
    clean = mask(sql)
    for m in re.finditer('[，；：（）]', clean):
        add('FULLWIDTH', 'error', '确定性语法错误', 'SQL 代码中存在中文全角标点。', '替换为对应英文半角标点；字符串中的中文标点无需修改。', offset=m.start())
    try:
        tokens = sqlglot.Tokenizer(dialect='spark').tokenize(prepare(sql))
        for index, token in enumerate(tokens):
            if token.token_type.name != 'GROUP_BY': continue
            depth = 0
            previous = None
            for current in tokens[index + 1:]:
                kind = current.token_type.name
                if depth == 0 and kind in ('R_PAREN', 'HAVING', 'ORDER_BY', 'LIMIT', 'UNION', 'SEMICOLON', 'QUALIFY'):
                    break
                if kind == 'L_PAREN': depth += 1
                elif kind == 'R_PAREN': depth -= 1
                previous = current
            if previous and previous.token_type.name == 'COMMA':
                add('GROUP_TRAILING_COMMA', 'error', '确定性语法错误', 'group by 字段列表末尾有多余逗号。', '删除末尾逗号。', offset=previous.start)
    except sqlglot.errors.TokenError:
        pass
    prepared = prepare(sql)
    try:
        trees = sqlglot.parse(prepared, read='spark')
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError) as exc:
        for e in getattr(exc, 'errors', [{'description': str(exc)}]):
            issues.append(dict(code='PARSE', severity='error', category='解析器错误（需核对 DLI 方言）', line=e.get('line', 1), column=e.get('col', 1), reason=e.get('description', str(exc)), suggestion='核对括号、逗号和语句结构；若为 DLI 专有语法，请在 DLI 验证。'))
        trees = []
    for tree in trees:
        if tree is None: continue
        for scope in traverse_scope(tree):
            select = scope.expression
            if not isinstance(select, exp.Select): continue
            aliases = set(scope.sources)
            outer = scope.parent
            while outer:
                aliases.update(outer.sources)
                outer = outer.parent
            for col in scope.columns:
                if col.table and col.table not in aliases:
                    add('UNDEFINED_ALIAS', 'error', '静态结构错误', f'表别名 {col.table} 未在当前或外层作用域定义（也可能是结构体字段访问）。', '核对别名拼写和作用域；结构体字段需结合表结构验证。', col)
            for join in select.args.get('joins', []):
                on = join.args.get('on')
                if on:
                    for eq in on.find_all(exp.EQ):
                        if isinstance(eq.this, exp.Column) and isinstance(eq.expression, exp.Column) and eq.this == eq.expression:
                            add('SELF_JOIN_CONDITION', 'warning', '静态风险', 'join 条件两侧引用同一个字段，无法关联左右两表。', '确认是否应使用另一表别名；不要自动替换业务条件。', eq)
                add('JOIN_MULTIPLICATION', 'warning', '需要数据库验证', 'join 可能因连接键重复或缺少关联条件放大行数。', '检查双方连接键唯一性、空值和匹配基数，比较 join 前后行数。', join)
            group = select.args.get('group')
            if group and not any(isinstance(g, exp.Literal) or g.find(exp.Rollup, exp.Cube) for g in group.expressions):
                grouped = {g.sql(dialect='spark') for g in group.expressions}
                for item in select.expressions:
                    value = item.this if isinstance(item, exp.Alias) else item
                    if value.find(exp.Window) or not value.find(exp.Column): continue
                    if value.sql(dialect='spark') in grouped or item.alias in grouped: continue
                    cols = [c for c in value.find_all(exp.Column) if not c.find_ancestor(exp.AggFunc)]
                    if not cols: continue
                    if all(c.sql(dialect='spark') in grouped for c in cols): continue
                    add('GROUP_NON_AGGREGATE', 'warning', '静态风险', '输出表达式可能包含未分组的非聚合字段。', '确认字段属于 group by，或按业务含义使用聚合；复杂表达式需在 DLI 验证。', value)
        for div in tree.find_all(exp.Div):
            denominator = div.expression
            if isinstance(denominator, exp.Nullif): continue
            add('DIVISION_ZERO', 'warning', '静态风险', '除数可能为零；实际行为依赖 DLI 配置。', '确认零值处理，可使用 nullif(除数, 0)；case when 防护需人工核对。', denominator)
        for between in tree.find_all(exp.Between):
            add('DATE_BOUNDARY', 'info', '静态风险', 'between 包含两个端点；用于日期或时间区间时需核对边界。', '时间戳按天筛选可采用 >= 起日 and < 次日；核对字段类型。', between)
        for compare in tree.find_all(exp.LTE, exp.LT, exp.GTE, exp.GT):
            if re.search(r'\d{4}-\d{2}-\d{2}|v{5,}', compare.sql()):
                add('DATE_BOUNDARY', 'info', '静态风险', '日期或模板区间的端点需要核对。', '核对包含/排除端点、模板值和日期/时间戳类型。', compare)
    try:
        for v in Linter(config=CONFIG).lint_string(prepared).get_violations():
            code = v.rule_code()
            issues.append(dict(code='FLUFF_' + code, severity='warning' if code in ('PRS', 'LXR') else 'info', category='方言兼容提示' if code in ('PRS', 'LXR') else '格式建议', line=v.line_no, column=v.line_pos, reason=v.desc(), suggestion='核对 Spark/DLI 语法。' if code in ('PRS', 'LXR') else '点击格式化查看小写关键字、前置逗号和缩进建议。'))
    except Exception:
        add('LINT_FAILED', 'warning', '工具限制', 'SQLFluff 未完成检查。', '缩小 SQL 范围后重试。')
    issues.sort(key=lambda x: (x['line'], x['column'], x['code']))
    return {'issues': issues, 'statement_count': len(trees), 'limitations': '不执行 SQL。表/字段存在性、字段类型、权限、函数签名、分区、连接基数及执行计划必须在数据库验证。解析成功不代表 DLI 可执行。'}

def format_sql(sql):
    replacements = {}
    def replace(m):
        token = 'sqlchecktemplate' + str(len(replacements))
        while token in sql: token += 'x'
        replacements[token] = m.group()
        return token
    prepared = re.sub(r'\$\{[A-Za-z_][A-Za-z0-9_]*\}', replace, sql)
    result = Linter(config=CONFIG).lint_string(prepared, fix=True)
    if any(v.rule_code() in ('PRS', 'LXR') for v in result.get_violations()):
        raise ValueError('存在无法解析的语法，已保留原文，请先处理错误。')
    formatted = result.fix_string()[0]
    for token, original in replacements.items(): formatted = formatted.replace(token, original)
    # Lexical equivalence is required: no token/literal/comment changes except keyword case.
    before = sqlglot.Tokenizer(dialect='spark').tokenize(prepare(sql))
    after = sqlglot.Tokenizer(dialect='spark').tokenize(prepare(formatted))
    if [(t.token_type, t.text if t.token_type.name in ('STRING', 'IDENTIFIER') else t.text.lower(), t.comments) for t in before] != [(t.token_type, t.text if t.token_type.name in ('STRING', 'IDENTIFIER') else t.text.lower(), t.comments) for t in after]:
        raise ValueError('格式化改变了词法结构，已拒绝输出。')
    return formatted
