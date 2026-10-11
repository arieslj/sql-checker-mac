"""Offline Spark SQL analysis. No execution, network, or persistence."""
import re
import hashlib
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope
from sqlfluff.core import FluffConfig, Linter

CONFIG = FluffConfig(configs={"core": {"dialect": "sparksql", "templater": "raw", "rules": "CP01,LT01,LT02,LT04"}, "rules": {"capitalisation.keywords": {"capitalisation_policy": "lower"}}, "layout": {"type": {"comma": {"line_position": "leading"}}}})

def template_tokens(sql):
    # Equal-width, distinct markers preserve both source locations and identity.
    mapping = {}
    reverse = {}
    def substitute(match):
        variable = match.group()
        if variable in mapping: return mapping[variable]
        width, salt = len(variable), 0
        while True:
            digest = hashlib.sha256(f'{variable}:{salt}'.encode()).hexdigest()
            marker = ('v' + digest * (1 + width // len(digest)))[:width]
            if marker not in sql and not any(marker in other or other in marker for other in reverse): break
            salt += 1
        mapping[variable] = marker
        reverse[marker] = variable
        return marker
    prepared = re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", substitute, sql)
    return prepared, reverse

def prepare(sql):
    return template_tokens(sql)[0]

def mask(sql):
    pattern = r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|\\.|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`"
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), sql)

def join_alias_issues(select):
    """Conservative ON checks. Previous aliases are legal; flag suspicious key use."""
    result = []
    def report(code, reason, suggestion, column=None):
        offset = column.args.get('table').meta.get('start') if column is not None and column.args.get('table') is not None else None
        result.append((code, reason, suggestion, column, offset))
    def terms(node):
        if isinstance(node, exp.Paren):
            yield from terms(node.this)
        elif isinstance(node, exp.And):
            yield from terms(node.this)
            yield from terms(node.expression)
        else:
            yield node
    origin = select.args.get('from_')
    previous = {origin.this.alias_or_name.lower()} if origin and origin.this.alias_or_name else set()
    local = {j.this.alias_or_name.lower() for j in select.args.get('joins', []) if j.this.alias_or_name} | previous
    for join in select.args.get('joins', []):
        name = join.this.alias_or_name
        current = name.lower()
        on = join.args.get('on')
        if not name or on is None:
            if name: previous.add(current)
            continue
        equalities = [t for t in terms(on) if isinstance(t, exp.EQ) and isinstance(t.this, exp.Column) and isinstance(t.expression, exp.Column)]
        available = previous | {current}
        # Future joins cannot be referenced by this ON, even if globally declared.
        for col in on.find_all(exp.Column):
            if col.find_ancestor(exp.Select) is not select: continue
            if col.table and col.table.lower() in local and col.table.lower() not in available:
                report('JOIN_ALIAS_OUT_OF_SCOPE', f'连接 {name} 的 on 条件引用了尚未加入的别名 {col.table}。', '按连接顺序核对别名；将条件放到相关表加入之后，不自动改变业务逻辑。', col)
        direct_columns = [c for eq in equalities for c in (eq.this, eq.expression)]
        has_unqualified = any(not c.table for c in direct_columns)
        # Skip complex subquery predicates: correlation needs separate scope analysis.
        has_subquery = on.find(exp.Select) is not None
        uses_current = any(c.table.lower() == current for c in on.find_all(exp.Column) if c.find_ancestor(exp.Select) is select)
        if equalities and not uses_current and not has_unqualified and not has_subquery:
            col = next((c for c in direct_columns if c.table.lower() in previous), direct_columns[0])
            report('JOIN_TARGET_NOT_REFERENCED', f'正在连接 {name}，但 on 条件未引用当前连接表 {name} 的字段；可能误用了其他表别名。', f'核对每个关联项是否应引用 {name}；如为有意只筛选左表，请人工确认连接基数。', col)
        anchors = set()
        for eq in equalities:
            a, b = eq.this, eq.expression
            if a.table.lower() == current and b.table.lower() in previous: anchors.add(b.table.lower())
            if b.table.lower() == current and a.table.lower() in previous: anchors.add(a.table.lower())
        for eq in equalities:
            a, b = eq.this, eq.expression
            if not a.table or not b.table or a.name.lower() != b.name.lower(): continue
            if a.table.lower() == b.table.lower() or not {a.table.lower(), b.table.lower()} <= previous: continue
            candidates = [c for c, other in ((a, b), (b, a)) if other.table.lower() in anchors and c.table.lower() not in anchors]
            if len(candidates) != 1: continue
            wrong = candidates[0]
            corrected = eq.copy()
            replacement = corrected.this if wrong is a else corrected.expression
            alias_node = join.this.args.get('alias')
            identifier = alias_node.this if alias_node else getattr(join.this, 'this', None)
            replacement.set('table', identifier.copy() if isinstance(identifier, exp.Identifier) else exp.to_identifier(name))
            report('JOIN_KEY_ALIAS_MISMATCH', f'正在连接 {name}；该关联项 {eq.sql(dialect="spark")} 只比较已连接的表，未引用 {name}，疑似复制了别名 {wrong.table}。', f'请优先核对是否应改为 {corrected.sql(dialect="spark")}。其他已连接表可以合法用于 on，此处是同名连接键的高优先级风险，不是确定性语法错误；不会自动替换。', wrong)
        previous.add(current)
    return result

def group_consistency_issues(select, template_reverse=None):
    """Compare grouping expressions with local non-aggregate output dependencies."""
    def display(node):
        text = node.sql(dialect='spark')
        for marker, original in sorted((template_reverse or {}).items(), key=lambda pair: -len(pair[0])):
            text = text.replace(marker, original)
        return text
    result = []
    group = select.args.get('group')
    def emit(code, severity, reason, suggestion, node, priority=0):
        result.append((code, severity, reason, suggestion, node, priority))
    def local_nodes(node):
        yield node
        for child in node.iter_expressions():
            if isinstance(child, (exp.Select, exp.Subquery)): continue
            yield from local_nodes(child)
    def global_aggregate(node):
        for item in local_nodes(node):
            if not isinstance(item, exp.AggFunc): continue
            parent = item.parent
            nested_aggregate = False
            while parent is not None and parent is not select:
                if isinstance(parent, exp.AggFunc): nested_aggregate = True
                if isinstance(parent, exp.Window):
                    if nested_aggregate: return True
                    break
                parent = parent.parent
            else:
                return True
        return False
    has_aggregate = any(global_aggregate(item) for item in select.expressions)
    for clause in ('having', 'order'):
        if select.args.get(clause) and global_aggregate(select.args[clause]): has_aggregate = True
    where = select.args.get('where')
    if where is not None:
        for node in local_nodes(where):
            if isinstance(node, exp.AggFunc):
                emit('WHERE_AGGREGATE', 'error', f'where 中直接使用了聚合表达式 {display(node)}。', '行级条件放在 where，聚合后的过滤按业务含义使用 having 或外层查询。', node)
    if group is None and not has_aggregate: return result
    if group is not None and group.args.get('all'):
        emit('GROUP_COMPLEX_UNVERIFIED', 'warning', 'group by all 的支持取决于 DLI 引擎版本，本次不作普通分组判定。', '核对 DLI 引擎版本，建议使用明确的分组项。', group, 2)
        return result
    advanced = group is not None and group.find(exp.Rollup, exp.Cube, exp.GroupingSets) is not None
    def dimensions(node):
        # Only flatten grouping containers, never scalar expressions or functions.
        if isinstance(node, (exp.Rollup, exp.Cube, exp.GroupingSets, exp.Tuple)):
            for child in node.expressions: yield from dimensions(child)
        elif isinstance(node, exp.Paren):
            yield from dimensions(node.this)
        else:
            yield node
    group_items = []
    if group is not None:
        for item in group.expressions: group_items.extend(dimensions(item))
        for kind in ('rollup', 'cube', 'grouping_sets'):
            for item in group.args.get(kind) or []: group_items.extend(dimensions(item))
    # Columns absent from individual grouping sets may legally become NULL.
    # Consistency is checked against the union, not each subtotal separately.
    source = select.args.get('from_')
    names = [source.this.alias_or_name.lower()] if source and source.this.alias_or_name else []
    names += [j.this.alias_or_name.lower() for j in select.args.get('joins', []) if j.this.alias_or_name]
    sole_source = names[0] if len(names) == 1 else None
    def key(node, unqualified=False):
        def normalize(item):
            if isinstance(item, exp.Paren): return item.this
            if isinstance(item, exp.Identifier): item.set('this', item.this.lower())
            if isinstance(item, exp.Column) and (unqualified or sole_source and item.table.lower() == sole_source):
                for part in ('table', 'db', 'catalog'): item.set(part, None)
            return item
        return node.copy().transform(normalize).sql(dialect='spark')
    aliases = {}
    for item in select.expressions:
        if isinstance(item, exp.Alias): aliases.setdefault(item.alias.lower(), []).append(item.this)
    keys = {}
    dimension_resolution = {}
    uncertain = False
    for item in group_items:
        value = item
        resolved_alias = False
        if isinstance(item, exp.Column) and not item.table and item.name.lower() in aliases:
            choices = aliases[item.name.lower()]
            if len(choices) != 1:
                emit('GROUP_ALIAS_AMBIGUOUS', 'warning', f'group by 别名 {item.name} 对应多个输出表达式，无法可靠核对。', '为输出表达式使用唯一别名，再核对分组含义。', item)
                uncertain = True
                continue
            candidate = choices[0]
            # An aggregate alias equal to one of its input names may also be a
            # real input column; avoid declaring a legal physical key invalid.
            input_collision = any(isinstance(n, exp.Column) and n.name.lower() == item.name.lower() for n in local_nodes(candidate))
            if isinstance(candidate, exp.AggFunc) and input_collision:
                value = item
            else:
                value = candidate
                resolved_alias = True
        elif isinstance(item, exp.Literal) and item.is_int:
            position = int(item.this)
            if position < 1 or position > len(select.expressions):
                emit('GROUP_POSITION_INVALID', 'error', f'group by 序号 {position} 超出 select 输出列表范围。', '核对输出位置及 spark.sql.groupByOrdinal 配置，建议使用明确的分组表达式。', item)
                uncertain = True
                continue
            target = select.expressions[position - 1]
            value = target.this if isinstance(target, exp.Alias) else target
        if any(isinstance(n, exp.Star) for n in local_nodes(value)):
            emit('GROUP_WILDCARD_UNVERIFIED', 'warning', '分组/输出包含星号，离线无法确定实际列与序号。', '展开明确字段后核对，或结合数据库表结构验证。', item)
            uncertain = True
            continue
        if any(isinstance(n, (exp.AggFunc, exp.Window)) for n in local_nodes(value)):
            emit('GROUP_AGGREGATE_KEY', 'warning' if resolved_alias else 'error', f'group by 项 {display(item)} 按输出别名解析为聚合或窗口表达式。' if resolved_alias else f'group by 项 {display(item)} 包含聚合或窗口表达式。', '分组应使用输入维度，核对输出别名、序号与表结构；聚合表达式留在输出或 having 中。', item)
            uncertain = True
            continue
        dimension_resolution[key(item)] = key(value)
        keys[key(value)] = (item, value)
    if uncertain: return result
    if group is not None and group.args.get('grouping_sets'):
        active = set()
        for container in group.args['grouping_sets']:
            active.update(dimension_resolution.get(key(item), key(item)) for item in dimensions(container))
        for container in group.expressions:
            for item in dimensions(container):
                resolved = dimension_resolution.get(key(item), key(item))
                if resolved not in active and any(isinstance(n, exp.Column) for n in local_nodes(item)):
                    emit('GROUP_KEY_ALWAYS_NULL', 'warning', f'前置 group by 维度 {display(item)} 未出现在 grouping sets 的任意集合中。', '兼容分组语义下该维度可能在所有结果行中为 NULL；核对 DLI 引擎与集合配置是否符合业务需求。', item)
    used = set()
    unknown_star = False
    outputs = [(item.this if isinstance(item, exp.Alias) else item, 'select') for item in select.expressions]
    for name in ('having', 'order'):
        if select.args.get(name) is not None: outputs.append((select.args[name], name))
    for value, clause in outputs:
        missing = []
        ambiguous = []
        resolving_aliases = set()
        def validate(node, window_function=False):
            nonlocal unknown_star
            if isinstance(node, (exp.Select, exp.Subquery)): return
            if isinstance(node, (exp.Grouping, exp.GroupingId)):
                arguments = node.expressions
                def argument_key(argument):
                    if isinstance(argument, exp.Column) and not argument.table:
                        candidates = aliases.get(argument.name.lower(), [])
                        if len(candidates) == 1 and key(candidates[0]) in keys: return key(candidates[0])
                    return key(argument)
                argument_keys = [argument_key(a) for a in arguments]
                used.update(k for k in argument_keys if k in keys)
                if not advanced:
                    emit('GROUPING_CONTEXT_INVALID', 'error', f'{display(node)} 只能用于多维分组上下文。', '配合 rollup/cube/grouping sets 使用，并核对 DLI 版本。', node)
                elif any(k not in keys for k in argument_keys):
                    emit('GROUPING_ARGUMENT_INVALID', 'error', f'{display(node)} 引用了未声明的分组维度。', '参数必须与实际分组表达式对应；按表达式分组时不能仅使用其内部原始字段。', node)
                elif isinstance(node, exp.GroupingId) and arguments and argument_keys != list(keys):
                    emit('GROUPING_ID_ARGUMENTS', 'warning', f'{display(node)} 的参数顺序/完整性与分组维度不一致。', '常见 Spark 语义要求参数与分组维度同序且完整；也可使用无参数 grouping_id()，请在 DLI 核对。', node)
                elif isinstance(node, exp.Grouping) and len(arguments) != 1:
                    emit('GROUPING_ARGUMENT_INVALID', 'error', 'grouping() 应指定一个分组表达式。', '为每个维度分别调用 grouping(分组表达式)。', node)
                return
            canonical = key(node)
            if canonical in keys:
                used.add(canonical)
                return
            if len(names) > 1:
                for group_key, (_, expression) in keys.items():
                    if key(node, unqualified=True) != key(expression, unqualified=True): continue
                    left = [n for n in local_nodes(node) if isinstance(n, exp.Column)]
                    right = [n for n in local_nodes(expression) if isinstance(n, exp.Column)]
                    if len(left) != len(right) or not left: continue
                    if all(a.table.lower() == b.table.lower() or not a.table or not b.table for a,b in zip(left,right)) and any(bool(a.table) != bool(b.table) for a,b in zip(left,right)):
                        ambiguous.append(node)
                        used.add(group_key)
                        return
            if isinstance(node, exp.Star) or isinstance(node, exp.Column) and isinstance(node.this, exp.Star):
                unknown_star = True
                return
            if isinstance(node, exp.Window):
                validate(node.this, window_function=True)
                for name, argument in node.args.items():
                    if name == 'this': continue
                    if isinstance(argument, exp.Expression): validate(argument)
                    elif isinstance(argument, list):
                        for child in argument:
                            if isinstance(child, exp.Expression): validate(child)
                return
            if isinstance(node, (exp.Filter, exp.WithinGroup)):
                function = node.this
                while isinstance(function, (exp.Filter, exp.WithinGroup)): function = function.this
                if isinstance(function, exp.AggFunc) and not window_function: return
                validate(node.this, window_function)
                for child in node.iter_expressions():
                    if child is not node.this: validate(child)
                return
            if isinstance(node, exp.AggFunc) and not window_function: return
            if isinstance(node, exp.Column):
                if clause != 'select' and not node.table and node.name.lower() in aliases:
                    alias_name = node.name.lower()
                    if len(aliases[alias_name]) == 1 and alias_name not in resolving_aliases:
                        resolving_aliases.add(alias_name)
                        validate(aliases[alias_name][0])
                        resolving_aliases.remove(alias_name)
                        return
                missing.append(node)
                return
            for child in node.iter_expressions(): validate(child)
        previous_used = set(used)
        validate(value)
        if clause != 'select': used = previous_used
        if ambiguous:
            emit('GROUP_COLUMN_AMBIGUOUS', 'warning', f'输出 {display(value)} 与 group by 存在同名但限定方式不同的字段；多表来源下无法离线确认是否相同。', '结合表结构核对裸字段实际来源，建议在 select 和 group by 明确使用相同表别名。', ambiguous[0])
        if missing:
            fields = ', '.join(dict.fromkeys(display(c) for c in missing))
            if clause != 'select':
                emit('GROUP_CLAUSE_NON_AGGREGATE', 'error', f'{clause} 包含未被分组覆盖的非聚合字段：{fields}。', '使用分组维度、合法输出别名或聚合表达式核对该条件/排序项。', missing[0])
            elif group is None:
                emit('GROUP_BY_MISSING', 'error', f'当前查询混用聚合与非聚合输出 {fields}，但没有 group by。', '按业务统计维度添加 group by，或将对应输出改为符合业务含义的聚合表达式。', missing[0])
            else:
                emit('GROUP_NON_AGGREGATE', 'error', f'select 输出 {display(value)} 包含未被 group by 覆盖的非聚合字段：{fields}。', '核对 select 与 group by 的字段和完整表达式；将其纳入正确分组维度或按业务含义聚合，确认统计粒度。', missing[0])
    if unknown_star:
        emit('GROUP_WILDCARD_UNVERIFIED', 'warning', '聚合查询使用 *，无法离线确认输出列与 group by 是否一致。', '展开明确字段，结合表结构核对非聚合列。', select.expressions[0])
    if has_aggregate and group is not None and not unknown_star:
        for canonical, (item, value) in keys.items():
            if canonical not in used and any(isinstance(n, exp.Column) for n in local_nodes(value)):
                emit('GROUP_KEY_NOT_PROJECTED', 'warning', f'group by 维度 {display(item)} 未在非聚合输出中体现，结果可能存在隐藏分组粒度。', '这在 SQL 中可以合法；确认该维度是否为有意分组，是否需要在 select 展示，勿自动删除分组项。', item)
    return result


def analyze(sql):
    issues = []
    def add(code, level, category, reason, suggestion, node=None, offset=None, priority=None):
        meta = (node.meta if node else {})
        if node and not meta:
            meta = next((x.meta for x in node.walk() if x.meta.get('line')), {})
        line, column = meta.get('line', 1), meta.get('col', 1)
        if offset is not None:
            line = sql.count('\n', 0, offset) + 1
            column = offset - sql.rfind('\n', 0, offset)
        issues.append(dict(code=code, severity=level, category=category, line=line, column=column, reason=reason, suggestion=suggestion, **({'priority': priority} if priority is not None else {})))
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
    prepared, template_reverse = template_tokens(sql)
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
            for code, reason, suggestion, col, offset in join_alias_issues(select):
                add(code, 'error', '高优先级关联风险' if code != 'JOIN_ALIAS_OUT_OF_SCOPE' else '静态结构错误', reason, suggestion, col, offset, priority=0)
            for join in select.args.get('joins', []):
                on = join.args.get('on')
                if on:
                    for eq in on.find_all(exp.EQ):
                        if isinstance(eq.this, exp.Column) and isinstance(eq.expression, exp.Column) and eq.this == eq.expression:
                            add('SELF_JOIN_CONDITION', 'warning', '静态风险', 'join 条件两侧引用同一个字段，无法关联左右两表。', '确认是否应使用另一表别名；不要自动替换业务条件。', eq)
                add('JOIN_MULTIPLICATION', 'warning', '需要数据库验证', 'join 可能因连接键重复或缺少关联条件放大行数。', '检查双方连接键唯一性、空值和匹配基数，比较 join 前后行数。', join)
            for code, severity, reason, suggestion, node, priority in group_consistency_issues(select, template_reverse):
                category = '高优先级聚合一致性错误' if severity == 'error' else '分组粒度风险' if code == 'GROUP_KEY_NOT_PROJECTED' else '分组验证提示'
                metadata = next((part.meta for part in node.walk() if part.meta.get('start') is not None), {})
                add(code, severity, category, reason, suggestion, node, offset=metadata.get('start'), priority=priority)
        for div in tree.find_all(exp.Div):
            denominator = div.expression
            if isinstance(denominator, exp.Nullif): continue
            add('DIVISION_ZERO', 'warning', '静态风险', '除数可能为零；实际行为依赖 DLI 配置。', '确认零值处理，可使用 nullif(除数, 0)；case when 防护需人工核对。', denominator)
        for between in tree.find_all(exp.Between):
            add('DATE_BOUNDARY', 'info', '静态风险', 'between 包含两个端点；用于日期或时间区间时需核对边界。', '时间戳按天筛选可采用 >= 起日 and < 次日；核对字段类型。', between)
        for compare in tree.find_all(exp.LTE, exp.LT, exp.GTE, exp.GT):
            if re.search(r'\d{4}-\d{2}-\d{2}', compare.sql()) or any(marker in compare.sql() for marker in template_reverse):
                add('DATE_BOUNDARY', 'info', '静态风险', '日期或模板区间的端点需要核对。', '核对包含/排除端点、模板值和日期/时间戳类型。', compare)
    try:
        for v in Linter(config=CONFIG).lint_string(prepared).get_violations():
            code = v.rule_code()
            issues.append(dict(code='FLUFF_' + code, severity='warning' if code in ('PRS', 'LXR') else 'info', category='方言兼容提示' if code in ('PRS', 'LXR') else '格式建议', line=v.line_no, column=v.line_pos, reason=v.desc(), suggestion='核对 Spark/DLI 语法。' if code in ('PRS', 'LXR') else '点击格式化查看小写关键字、前置逗号和缩进建议。'))
    except Exception:
        add('LINT_FAILED', 'warning', '工具限制', 'SQLFluff 未完成检查。', '缩小 SQL 范围后重试。')
    for issue in issues:
        issue.setdefault('priority', {'error': 1, 'warning': 2, 'info': 3}[issue['severity']])
    issues.sort(key=lambda x: (x['priority'], x['line'], x['column'], x['code']))
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
