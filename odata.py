"""
Starting with features listed here:
https://github.com/ResistanceCalendar/resistance-calendar-api

>>> import odata
>>> processor = odata.FilterProcessor(odata.DjangoQueryAdapter())
>>> for t in odata.TESTS: print(processor.process(t))
(AND: ('start_date__gt', '2017-03-01'))
(AND: ('start_date__gte', '2017-03-01'), ('start_date__lt', '2017-03-02'))
(AND: ('location__postal_code', '22980'))
(OR: ('name__contains', 'Sessions'), ('name__contains', 'DeVos'))
(AND: ('location__postal_code', '22980'), (OR: ('name__contains', 'Sessions'), ('name__contains', 'DeVos')))
(AND: (OR: ('name__contains', 'Sessions'), ('name__contains', 'DeVos')), ('location__postal_code', '22980'))
>>>

"""
from parsimonious.grammar import Grammar


class ODataException(Exception):
    pass


TESTS = [
    """foo eq 1""",
    #WRONG: <Q: (AND: ('foo__isnull', True))>
    """start_date gt '2017-03-01'""",
    """start_date ge '2017-03-01' and start_date lt '2017-03-02'""",
    """location/postal_code eq '22980'""",
    """contains(name, 'Sessions') or contains(name, 'DeVos')""",
    """location/postal_code eq '22980' and (contains(name, 'Sessions') or contains(name, 'DeVos'))""",
    """(contains(name, 'Sessions') or contains(name, 'DeVos')) and location/postal_code eq '22980'"""]


def django_filter(filter_text, field_mapper=None):
    """
    accepts a $filter argument, and translates it to a django Q object to pass into a filter
    if a field_mapper is passed in, we can map fields beyond naive transposition
    """
    processor = FilterProcessor(DjangoQueryAdapter(field_mapper))
    return processor.process(filter_text)

grammar = Grammar(
    # explicitly missing:
    # hasExpr, arithmetic operators
    # explicitly papering over: concat() can be nested
    # wtf: "Items/all(d:d/Quantity gt 100)"
    # functions like "now()" can have no arguments
    """
    boolCommonExpr = (notExpr / commonExpr ) ( andExpr / orExpr )?
    relExpr         = (functionParam / functionExpr) RWS relMarker RWS functionParam
    relMarker      = 'eq' / 'ne' / 'lt' / 'le' / 'gt' / 'ge'
    xcommonExpr  = ~"[\w/',() ]+"
    xtokens  = ~"[\w/']+"
    commonExpr    = parenExpr / functionExpr / relExpr
    functionExpr   = funcName "(" ~"\s*" functionParam  (~"\s*,\s*" functionParam)* ~"\s*" ")"
    funcName       = ~"\w+"
    selectPath     = ~"[a-zA-Z][\w/]*"
    number         = "-"? ~"[\d.+]"
    string         = "'" ~"[^']+" "'"
    jsonPrimitive  = "true" / "false" / "null"
    functionParam = number / string / jsonPrimitive / selectPath
    parenExpr      = "(" ~"\s*" boolCommonExpr ~"\s*" ")"
    notExpr        = 'not' RWS boolCommonExpr
    andExpr        = RWS 'and' RWS boolCommonExpr
    orExpr         = RWS 'or' RWS boolCommonExpr
    RWS            = ~"\s+"
    """)


functionParam = ['selectPath', 'number', 'string', 'jsonPrimitive']  # param or token
# which parsed nodes the key actually cares about
good_children = {
    'boolCommonExpr': ['notExpr', 'commonExpr', 'andExpr', 'orExpr'],
    'commonExpr': ['parenExpr', 'functionExpr', 'relExpr'],
    'functionExpr': ['funcName'] + functionParam,
    'relExpr': ['relMarker', 'functionExpr'] + functionParam,
    'parenExpr': ['boolCommonExpr'],
    'orExpr': ['boolCommonExpr'],
    'andExpr': ['boolCommonExpr'],
    'notExpr': ['boolCommonExpr'],
}


def walk(parsed, nodetype='boolCommonExpr', method=None):
    """
    Throws out junk in parse-tree, so each handler
    can get just the useful stuff.  This is depth-first
    because that's basically how the node-tree is structured
    """
    # .expr_name, .children, .text
    reduced_stack = []
    good = good_children[nodetype]
    for c in parsed.children:
        if method:
            method(c)
        if c.expr_name in good:
            # don't walk down good nodes, since they'll be handled
            # by handler
            reduced_stack.append(c)
        else:
            reduced_stack.extend(walk(c, nodetype, method))
    return reduced_stack


class DjangoQueryAdapter(object):
    """
    This is an adapter that just takes the inner parts used by the
    Processor class below.  You can create another adapter that implements
    the same functions here, and maybe generate something for SQLAlchemy, etc

    Args:
       field_mapper (function): takes a tuple of hierarchical field references
         so e.g. odata reference "location/address" will become ('location', 'address')
         Django's default is to join these references by '__'
         but you may want a custom one, to map serialized names to different fields,
         e.g. ('location', 'address') => just 'address' (because there is no location reference).
    """

    def __init__(self, field_mapper=None):
        from django.db.models import Q

        if field_mapper is None:
            field_mapper = lambda x: '__'.join(x)
        self.field_mapper = field_mapper
        self.Q = Q

    def bool_combinor(self, leftExpr, op, rightExpr=None):
        """
        Args:
           leftExpr: will be a Q object
           op (str): either 'not', 'and', 'or'
           rightExpr: if op is not 'not', then this is the rightside
        """
        ops = {
            'not': lambda a, b: ~a,
            'and': lambda a, b: a & b,
            'or': lambda a, b: a | b
        }
        return ops[op](leftExpr, rightExpr)

    def basic_relation(self, fields, op, value):
        """
        simple relation expressions like created_at gt '2017-01-01'
        """
        token = self.field_mapper(fields)
        if value is None:
            token = token + '__isnull'
            # a little hacky, but if op=='ne' then we just negate it below anyway
            value = True
        if op in ('lt', 'le', 'gt', 'ge'):
            if op in ('le', 'ge'):
                op = op[0] + 'te'  # ge=>gte, le=>lte
            token = '{}__{}'.format(token, op)
        qexpr = self.Q(**{token: value})
        if op == 'ne':
            qexpr = ~qexpr
        return qexpr

    def basic_function(self, funcname, fields, value):
        """
        This is for expressions like contains(reffield/field, 'blah')
        """
        token = self.field_mapper(fields)
        if funcname == 'contains':
            token = token + '__contains'
            return self.Q(**{token: value})


class FilterProcessor(object):

    def __init__(self, adapter):
        self.adapter = adapter

    def unpack(self, node):
        """go down a level: common use case"""
        return self.boolCommonExpr(walk(node, node.expr_name)[0])

    def process(self, filter_text):
        parsed = grammar.parse(filter_text)
        return self.boolCommonExpr(parsed)

    def boolCommonExpr(self, node):
        """
        This is the top expression parser
        """
        front, *pieces = walk(node, 'boolCommonExpr')
        qexpr = None
        if front.expr_name == 'notExpr':
            qexpr = self.adapter.bool_combinor(self.unpack(front), 'not')
        else:
            qexpr = self.commonExpr(front)
        if pieces:
            binExpr = pieces[0]
            addition = self.unpack(binExpr)
            qexpr = self.adapter.bool_combinor(
                qexpr,
                'and' if binExpr.expr_name == 'andExpr' else 'or',
                addition)
        return qexpr

    def commonExpr(self, node):
        """parenExpr, functionExpr, relExpr"""
        inner = walk(node, 'commonExpr')[0]
        if inner.expr_name == 'parenExpr':
            return self.unpack(inner)
        else:
            return getattr(self, inner.expr_name)(inner)

    def relExpr(self, node):
        """returns a Q object for the relationship"""
        args = {}
        pieces = walk(node, 'relExpr')
        if len(pieces) != 3 \
           or pieces[0].expr_name != 'selectPath' \
           or pieces[1].expr_name != 'relMarker':
            raise ODataException("unexpected expression structure should by 'X op Y'")
        #most normal structure is pieces = [<selectPath> <OP> <value>]
        if pieces[0].expr_name == 'selectPath':
            op = pieces[1].text
            fields = pieces[0].text.split('/')
            val = self.primitive(pieces[2])
            return self.adapter.basic_relation(fields, op, val)
        else:
            raise ODataException("unimplemented relation expression: '{}'".format(node.text))

    def primitive(self, node):
        if node.expr_name == 'string':
            return node.children[1].text  # string
        elif node.expr_name == 'number':
            dd = node.text
            if '.' in dd:
                return float(dd)
            else:
                return int(dd)
        elif node.expr_name == 'jsonPrimitive':
            cases = {
                'true': True,
                'false': False,
                'null': None}
            return cases[node.text]
        raise ODataException("unmatched primitive type '{}'".format(node.text))

    def functionExpr(self, node):
        """
        functions can be a full expression or part of one
        full expression functions: contains, startswith, indexof, endswith
        other expressions can be a string like concat() and length

        This one is just for the full expression values
        """
        funcname, *params = walk(node, 'functionExpr')
        param_vals = [(p.text.split('/') if p.expr_name == 'selectPath'
                       else self.primitive(p))
                      for p in params]
        if len(params) == 2 and params[0].expr_name == 'selectPath':
            return self.adapter.basic_function(funcname.text, *param_vals)
        else:
            raise ODataException("function not supported '{}'".format(node.text))


if __name__ == '__main__':
    import sys
    processor = FilterProcessor(DjangoQueryAdapter())
    if len(sys.argv) > 1:
        filter_text = sys.argv[1]
        if filter_text == 'doctest':
            import doctest
            doctest.testmod()
            print('doctests passed')
        else:
            print(processor.process(filter_text))
    else:
        for t in TESTS:
            print(processor.process(t))
